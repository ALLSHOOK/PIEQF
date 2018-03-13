#!/usr/bin/python

###
# Parkfield Interventional Earth-Quake Fieldwork
# 
# Vertical motion triggering program.
# Instantiates and runs a 'DASReader' instance (see dasreader.py) which
#	continuously reads samples from the first 3 inputs of a PCI-DAS)* A/D converter card.
#	For each block of samples read and for each input, calculates the standard-devaition
#	over each channel's input-buffer and converts this number to a pseudo-magnitude.
#	From the pseudo-magnitude, a duration is calculated in turn.
#	If a channel's pseudo-magnitude rises above the defined threshold, writes the channel-number, magnitude and duration to a FIFO
#	The FIFO (/tmp/pieqf-vert.fifo per default) is created if it doesn't yet exist.
#	This script will sleep until the other end of the FIFO is opened for reading.
#	This script also writes the events' metadata to a logfile (/var/log/pieqf/vtrigger.log. per default)
#
# The format of the data written to the FIFO is, one line per event:
#	CcMmmmDdddddddd
#	where 'C', 'M' and 'D' are literal characters, 'c' is the channel-number, 'mmm' is a 3-digit (magnitude * 10) value, 
#	and 'ddddddd' is the 8-digit duration value (in msec)
#
#	Stock, V2_Lab Rotterdam, July 2008
###

import os, sys, time, stat, signal

import dasreader

from optparse import OptionParser
	


if __name__ == '__main__':
	# Define default values
	default_logfile = "/var/log/pieqf/vtrigger.log"
	default_outfile = "pieqf-vert.out"
	default_fifo = "/tmp/pieqf-vert.fifo"
	default_channels = 4
	default_blksize = 4
	default_bufsize = 8
	default_thresh = 0.5
		
	progname = os.path.basename(sys.argv[0])
	
	op = OptionParser()
	
	# Define command-line options and arguments
	op.add_option("-l", "--logfile", action='store', type='string', dest='logfile', metavar='FILE',
					help="log activity to FILE [default = %s]" % default_logfile) 
	op.add_option("-o", "--out", action='store', type='string', dest='outfile', metavar='FILE',
					help="write output to FILE")
	op.add_option("-f", "--fifo", action='store', type='string', dest='fifo', metavar='FIFO',
					help="write output to FIFO [default = %s]" % default_fifo)
	op.add_option("-c", "--channels", action='store', type='int', dest='channels', metavar='N',
					help="set number of channels to sample [default = %d]" % default_channels)
	op.add_option("-b", "--bufsize", action='store', type='int', dest='bufsize', metavar='SIZE',
					help="set size of sample buffer [default = %d]" % default_bufsize)
	op.add_option("-s", "--blocksize", action='store', type='int', dest='blocksize', metavar='SIZE',
					help="set size of sample block [default = %d]" % default_blksize)
	op.add_option("-t", "--threshold", action='store', type='float', dest='thresh', metavar='MAG',
					help="set trigger threshold magnitude [default = %.1f]" % default_thresh)
	op.add_option("-u", "--utc", action='store_true', dest='utctime',
					help="log trigger events in UTC [default = local time]")
		
	# Set defaults
	op.set_defaults(logfile=default_logfile)
	op.set_defaults(fifo=default_fifo)
	op.set_defaults(channels=default_channels)
	op.set_defaults(bufsize=default_bufsize)
	op.set_defaults(blocksize=default_blksize)
	op.set_defaults(thresh=default_thresh)
	op.set_defaults(utctime=False)
	
	# Parse command-line options
	(opts, args) = op.parse_args()
	
	# Instantiate DASReader with given (or default) parameters
	dr = dasreader.DASReader(opts.channels, opts.bufsize, opts.blocksize)
	
	# Set trigger-threshold
	dr.setThreshold(opts.thresh)
	
	# Create an/or open logfile
	if opts.logfile == '-':
		logfd = sys.stdout
	else:
		logdir = os.path.dirname(opts.logfile)
		if logdir == '':
			logdir ='./'
		if os.path.basename(opts.logfile) == '':
			# the 'logfile' specified on the command-line is a directory. Use default logfile name
			logfile = os.path.join(logdir, os.path.basename(default_logfile))
		else:
			logfile = os.path.join(logdir, os.path.basename(opts.logfile))
		if not os.path.isdir(logdir):
			# the logfile's parent-dir does not exist yet.
			try:
				os.makedirs(logdir)
			except OSError, e:
				sys.stderr.write("Unable to create logfile dir '%s': %s\n" % (logdir, str(e)))
				
		if os.path.isdir(logdir):
			try:
				logfd = open(logfile, 'a', 1)	# append to file, line-buffered file
			except IOError, e:
				sys.stderr.write("Unable to create logfile '%s': %s\n" % (logfile, str(e)))
				logfd = sys.stdout
		else:
			# failed to create/find logfile's parent dir
			logfd = sys.stdout
			
	# Set the DASReader to write informational messages to the logfile
	dr.logfd = logfd
	dr.errfd = logfd
			
	# Define a signal-handler to stop the DASReader's threads
	def stophandler(sig, frame):
		logfd.write("\nGot signal %d\n" % sig)
		dr.stop()
	
	# Register signal-handler
	signal.signal(signal.SIGINT, stophandler)
	signal.signal(signal.SIGQUIT, stophandler)
	
	# Function to write triggered events to the logfile
	def printEvent(ch, mag, duration):
		out = ("%s: Triggered " % progname)
		if opts.utctime:
			out += "at %s" % time.strftime("%b %d %Y - %H:%M:%S UTC", time.gmtime())
		else:
			out += "at %s" % time.strftime("%b %d %Y - %H:%M:%S %Z", time.localtime())
		out += (" -> Channel %d, M%4.1f, D%7.1f s" % (ch, mag, duration))
		logfd.write(out + '\n')
		
	# Define a trigger-handler function.
	# writes events to logfile and to the FIFO/outfile
	def trig_func(ch, mag, duration):
		printEvent(ch, mag, duration)
		try:
			outfd.write("C%1dM%03dD%08d\n" % (ch, mag * 10, duration * 1000))
		except IOError, e:
			logfd.write("Error writing to %s: %s\n" % (outfile, str(e)))
	
	# Register the trigger-handler
	dr.setTrigFunc(trig_func)
	
	if opts.outfile:
		# Create and/or open the output-file
		outdir = os.path.dirname(opts.outfile)
		if outdir == '':
			outdir ='./'
		if os.path.basename(opts.outfile) == '':
			outfile = os.path.join(outdir, os.path.basename(default_outfile))
		else:
			outfile = os.path.join(outdir, os.path.basename(opts.outfile))
		if not os.path.isdir(outdir):
			try:
				os.makedirs(outdir)
			except OSError, e:
				sys.stderr.write("Unable to create outfile dir '%s': %s\n" % (outdir, str(e)))
				exit(1)
		
		try:
			outfd = open(outfile, 'w', 1)	# line-buffered file
		except IOError, e:
			sys.stderr.write("Unable to create outfile '%s': %s\n" % (outfile, str(e)))
			exit(1)
	
	else:
		# Create and/or open the output FIFO
		outdir = os.path.dirname(opts.fifo)
		if outdir == '':
			outdir ='./'
		if os.path.basename(opts.fifo) == '':
			outfile = os.path.join(outdir, os.path.basename(default_fifo))
		else:
			outfile = os.path.join(outdir, os.path.basename(opts.fifo))
		if not os.path.isdir(outdir):
			try:
				os.makedirs(outdir)
			except OSError, e:
				sys.stderr.write("Unable to create outfile dir '%s': %s\n" % (outdir, str(e)))
				exit(1)
		
		if os.path.exists(outfile):
			if not stat.S_ISFIFO(os.stat(outfile)[0]):
				sys.stderr.write("File '%s' exists, but is not a fifo\n" % outfile)
				exit(2)
		else:
			try:
				os.mkfifo(outfile)
			except OSError, e:
				sys.stderr.write("Unable to create fifo '%s': %s\n" % (outfile, str(e)))
				exit(1)
		
		try:
			outfd = open(outfile, 'w', 1)	# line-buffered file
							# this call blocks until the other end of the fifo is opened!
			timestring = time.strftime("%b %d %Y - %H:%M:%S UTC", time.gmtime())
			logfd.write("Fifo '%s' opened. Starting DASReader at %s\n" % (outfile, timestring))
		except IOError, e:
			sys.stderr.write("Unable to open fifo '%s' for writing: %s\n" % (fifo, str(e)))
			exit(3)
	
	# Start the DASReader's threads
	dr.start()
	
	# wait until dr is stopped or an exception occurs
	try:
		while dr.run:
			time.sleep(1)
				
	finally:
		logfd.write("Quitting\n")
		if dr.run:
			dr.stop()
		exit(0)
		
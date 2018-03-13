#!/usr/bin/python

###
# Parkfield Interventional Earth-Quake Fieldwork
# 
# Horizontal motion triggering program.
# Instantiates and runs a 'QDMTrigger' instance (see qdmparser.py) which
#	checks every second if the file /var/lib/QDM/catalog/merge.xml has been modified
#	If so, parses this XML-file and extracts the metedata fro all seismic events originating in the "NC' and 'CI' networks
#	If any new 'NC" or 'CI' events have appeared since last time, writes the events' Magnitude and Duration to a FIFO
#	The FIFO (/tmp/pieqf-hori.fifo per default) is created if it doesn't yet exist.
#	This script will sleep until the other end of the FIFO is opened for reading.
#	This script also writes the events' metadata to a logfile (/var/log/pieqf/htrigger.log. per default)
#
# The format of the data written to the FIFO is, one line per event:
#	C99MmmmDdddddddd
#	where 'M' and 'D' are literal characters, 'mmm' is a three-digit (magnitude * 10) value, and 'ddddddd' is the duration in msec
#
#	Stock, V2_Lab Rotterdam, July 2008
###

import os, sys, time, stat, signal

import qdmparser

from optparse import OptionParser
	


if __name__ == '__main__':
	# Define default values
	default_logfile = "/var/log/pieqf/htrigger.log"
	default_outfile = "pieqf-hori.out"
	default_fifo = "/tmp/pieqf-vert.fifo"
	
	progname = os.path.basename(sys.argv[0])
	
	op = OptionParser()
	
	# Define command-line options and arguments
	op.add_option("-l", "--logfile", action='store', type='string', dest='logfile', metavar='FILE',
					help="log activity to FILE [default = %s]" % default_logfile) 
	op.add_option("-o", "--out", action='store', type='string', dest='outfile', metavar='FILE',
					help="write output to FILE")
	op.add_option("-f", "--fifo", action='store', type='string', dest='fifo', metavar='FIFO',
					help="write output to FIFO [default = %s]" % default_fifo)
	op.add_option("-u", "--utc", action='store_true', dest='utctime',
					help="log trigger events in UTC [default = local time]")
	
	# Set defaults
	op.set_defaults(logfile=default_logfile)
	op.set_defaults(fifo=default_fifo)
	op.set_defaults(utctime=False)
	
	# Parse command-line options
	(opts, args) = op.parse_args()
	
	# Instantiate QDMTrigger, which is a subclass of QDMParser
	qt = qdmparser.QDMTrigger()
	
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
			
	# Define a signal-handler to stop the QDMTrigger's threads
	def stophandler(sig, frame):
		logfd.write("\nGot signal %d\n" % sig)
		qt.stop()
	
	# Define a signal-handler to reload the QDM catalog-file and the blacklist-file
	def reloadhandler(sig, frame):
		logfd.write("\nGot signal %d\n" % sig)
		qt.reload()
	
	# Register the signal-handlers
	signal.signal(signal.SIGINT, stophandler)
	signal.signal(signal.SIGQUIT, stophandler)
	signal.signal(signal.SIGHUP, reloadhandler)
	
	# Function to write triggered events to the logfile
	def printEvent(ev, duration):
		out = ("%s: Triggered" % progname).ljust(38)
		if opts.utctime:
			out += "at %s" % time.strftime("%b %d %Y - %H:%M:%S UTC\n", time.gmtime())
		else:
			out += "at %s" % time.strftime("%b %d %Y - %H:%M:%S %Z\n", time.localtime())
		out += ("-> Event %s:%s M%4.1f D%7.1f s" % (ev['net'], ev['id'], ev['mag'], duration)).ljust(38)
		out += "at %s" % time.strftime("%b %d %Y - %H:%M:%S UTC", time.localtime(ev['time']))
		out += ", %.3f,%.3f" % (ev['loc'][0], ev['loc'][1])
		if 'depth' in ev:
			out += ", %.1f km deep" % ev['depth']
		if 'dmin' in ev:
			out += ", %.1f km from nearest station" % ev['dmin']
		logfd.write(out + '\n')
		
	# Define a trigger-handler function.
	# writes events to logfile and to the FIFO/outfile
	def trig_func(events):
		for ev in events:
			if ev['mag'] <= 0:
				continue
			
			duration = 10**((ev['mag'] + 1.05) / 2.22)
			printEvent(ev, duration)
			try:
				outfd.write("C99M%03dD%08d\n" % (ev['mag'] * 10, duration * 1000))
			except IOError, e:
				logfd.write("Error writing to %s: %s\n" % (outfile, str(e)))
	
	# Register the trigger-handler
	qt.setTrigFunc(trig_func)
	
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
			logfd.write("Fifo '%s' opened. Starting QDMParser at %s\n" % (outfile, timestring))
		except IOError, e:
			sys.stderr.write("Unable to open fifo '%s' for writing: %s\n" % (fifo, str(e)))
			exit(3)
	
	# Stert the QDMTrigger & QDMParser threads
	qt.start()
	
	# wait until qt is stopped or an exception occurs
	try:
		while qt.run:
			time.sleep(1)
				
	finally:
		logfd.write("Quitting\n")
		if qt.run:
			qt.stop()
		exit(0)
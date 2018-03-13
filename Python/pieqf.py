#!/usr/bin/python

###
# Parkfield Interventional Earth-Quake Fieldwork
#
# This script combines all 3 elements; QDMParser, StpRunner and DASReader
#
# The QDMParser keeps a DB of the most recent seismic events of each magnitude.
# The StpRunner downloads seismograms fro the events in the DB
# The DASReader reads teh geophone-input(s) and, when triggered, looks-up
# the event with a corresponding magnitude in the DB.
# Finally, the triggered event's ID is passed to the output-application, which
# can then play-back the downloaded seismograms for that event on the shake-table.
#
#	Stock, V2_Lab Rotterdam, June 2008
###
import qdmparser, stprunner, dasreader

import sys, os, signal, threading

from optparse import OptionParser

if __name__ == '__main__':
	op = OptionParser()
	###
	# Command-line options
	###
	op.add_option("-v", "--verbose", action='store', type='string', dest='verbose', metavar='V',
					help="set verbosity (a bitmask) [default = 0]")
	op.add_option("-i", "--inputs", action='store', type='int', dest='num_ch', metavar='N',
					help="number of DAS08-inputs to listen on [default = 1]")
	op.add_option("-d", "--outputdir", action='store', type='string', dest='outputdir', metavar='DIR',
					help="save seismograms in DIR. (DIR will be created if it doesn't exist) [default = /var/lib/STP]")
	op.add_option("-n", "--threads", action='store', type='int', dest='num_thr', metavar='N',
					help="run at most N STP-threads (N >= 2) [default = 10]")
	op.add_option("-f", "--force", action='store_true', dest='force', 
					help="(re)download seismograms even if they exist")
	op.add_option("-s", "--stations", action='store', type='int', dest='num_sta', metavar='N',
					help="get seismograms from the N closest stations [default = 3]")
	op.add_option("-c", "--chan", action='append', type='string', dest='channels', metavar='CH',
					help="get seismograms from CH channels [default = H%]")
	op.add_option("-r", "--retper", action='store', type='string', dest='retper', metavar='T',
					help="retry unavailable events for T[s|m|h|d|w] sec|min|hours|days|weeks [default = 1d]")
	op.add_option("-k", "--keepper", action='store', type='string', dest='keepper', metavar='T',
					help="keep old events' seismogram-files for T[s|m|h|d|w] sec|min|hours|days|weeks [default = 30d]")
	op.add_option("-l", "--logfile", action='store', type='string', dest='logfile', metavar='FILE',
					help="write text-output to FILE. (FILE will be created if it doesn't exist) [default = /var/log/pieqf.log]")
	op.add_option("-b", "--bufsize", action='store', type='int', dest='bufsize', metavar='SIZE',
					help="set size of sample buffer [default = 15]")
	op.add_option("-z", "--blocksize", action='store', type='int', dest='blocksize', metavar='SIZE',
					help="set size of sample block [default = 10]")
	op.add_option("-t", "--threshold", action='store', type='float', dest='thresh', metavar='MAG',
					help="set trigger threshold magnitude [default = 0.1]")
	
	# Set default values	
	op.set_defaults(num_sta=3)
	op.set_defaults(num_thr=10)
	op.set_defaults(num_ch=1)
	op.set_defaults(channels='H%')
	op.set_defaults(retper='1d')
	op.set_defaults(keepper='30d')
	op.set_defaults(outputdir='/var/lib/STP')
	op.set_defaults(logfile='/var/log/pieqf.log')
	op.set_defaults(bufsize=15)
	op.set_defaults(blocksize=10)
	op.set_defaults(thresh=0.1)
	
	# Parse command-line options
	(opts, args) = op.parse_args()
	
	###
	# Instantiate main classes
	###
	
	qp = qdmparser.QDMParser()
	
	if opts.logfile == '-':
		sr = stprunner.StpRunner(qdmparser=qp, outputdir=opts.outputdir)
	else:
		sr = stprunner.StpRunner(qdmparser=qp, outputdir=opts.outputdir, logfile=opts.logfile, errfile=opts.logfile)
	
	dr = dasreader.DASReader(opts.num_ch, opts.bufsize, opts.blocksize)
	
	# share the log-file-object and err-file-object that the StpRunner created and opened with the DASReader
	dr.logfd = sr.logfd
	dr.errfd = sr.errfd
	
	###
	# process command-line options (or defaults)
	###
	
	if opts.verbose != None:
		# parse verbosity argument
		verbose = 0
		try:					# try binary first...
			verbose = int(opts.verbose, 2)
		except ValueError:
			try:				# ... then decimal...
				verbose = int(opts.verbose)
			except ValueError:	# ... then hexadecimal
				x = opts.verbose.find('x')
				hex = opts.verbose[(x + 1):]
				try:
					verbose = int(hex, 16)
				except ValueError:
					sys.stderr.write("Invalid verbosity argument '%s'" % opts.verbose)
	
		sr.setVerbose(verbose)
	
	# check max-number-of-threads argument
	if opts.num_thr > 1:
		sr.maxthreads = opts.num_thr
	else:
		raise ValueError("Invalid number-of-threads argument: %s" % str(opts.num_thr))
	
	# set retry- and retain-periods
	sr.setRetryPeriod(opts.retper)
	sr.setRetainPeriod(opts.keepper)
	
	# set trigger-threshold
	dr.setThreshold(opts.thresh)
		
	###
	# Signal-Handler functions
	###
	
	def stophandler(sig, frame):
		print "\nGot signal %d" % sig
		sr.stop()
	
	def reloadhandler(sig, frame):
		print "\nGot signal %d" % sig
		sr.reload()
	
	# Register signal handlers
	signal.signal(signal.SIGINT, stophandler)
	signal.signal(signal.SIGQUIT, stophandler)
	signal.signal(signal.SIGTERM, stophandler)
	signal.signal(signal.SIGHUP, reloadhandler)
	
	###
	# Trigger-Handler function
	###
	
	def trig_func(ch, mag, dur):
		event = qp.getEvent(mag)
		ev_str = sr._eventStr(event)
		dr.logMessage("! Triggered: Channel %d, Event %s, dur %.3f s" % (ch, ev_str, dur))
		
	# Register handler for trigger
	dr.setTrigFunc(trig_func)
		
	###
	# start QDMParser in its own thread
	###
	
	qp.start()
	
	###
	# start StpGarbageCollector in its own thread
	###
	
	sr.start()
	
	###
	# start DASReader in its own thread
	###
	
	dr.start()
	
	###
	# run the StpRunner's main-loop in the main-thread.
	###
	
	try:
		sr.runForever(opts.num_sta, opts.channels, opts.force)
		
	finally:
		print "Quitting"
		
		if dr.run:
			dr.stop()
		
		if qp.run:
			qp.stop()
		
		if sr.gcrun:
			sr.stop()
		
	exit(0)	
		

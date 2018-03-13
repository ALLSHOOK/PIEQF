#!/usr/bin/python

###
# Parkfield Interventional Earth-Quake Fieldwork
# 
# Defines the DASReader class for sampling the inputs of a PCI-DAS08 A/D converter card.
# Blocks of samples are read from each input and after each read block, the standard-deviation
# over each channel's sample buffer is caluclated and scaled down (/ 100) to a pseudo-magnitude value.
# if the pseudo-magnitude exceeds a settable threshold, a 'Trigger' callback-function is called
# with the channel-number, the pseudo-magnitude value and a duration calculated from the magnitude as arguments.
# The channels' bufsize is >= the blocksize 
# 
#	Stock, V2_Lab Rotterdam, June 2008
###
from __future__ import with_statement

import sys, time, struct, signal, threading
import numpy


class DASReader(object):
	"""Continuously reads samples from the channels of a PCI-DAS08 card.
	Calculates a pseudo-magnitude (standard-deviation / 100) over each channel's input-buffer
	after a block of samples has been read from all active channels. (bufsize >= blocksize)
	If the pseudo-magnitude exceeds the treshold, calls a trigger-function with the channel-number,
	pseudo-magnitude and duration (calculated from the magnitude) as arguments.
	"""
	threshold = 0.1
	
	# file-objects fro informational messages & warnings/errors
	logfd = sys.stdout
	errfd = sys.stderr
	
	def __init__(self, inputs=1, bufsize=15, blocksize=10):
		"""Instantiate a DASReader for the first 'inputs' inputs of the card
		(where 1 <= inputs <= 8)
		'bufsize' sets the size of the sample-buffer used to calulate the pseudo-magnitude
		'blocksize' sets the number of samples read in-between each calculation
		(bufsize >= blocksize)
		"""
		self.num_ch = min(max(1, inputs), 8)
		self.blocksize = blocksize
		self.bufsize = max(bufsize, blocksize)
		
		# define an array of size (num_ch x bufsize) as input-buffer
		self.buf = numpy.ndarray(shape=(self.num_ch, self.bufsize), dtype='int')
		# a list of write-pointers into the buffer
		self.buf_ptr = [0] * self.num_ch
		
		# an array of sixe (num_ch x 1) to store the channels' magnitudes
		self.mag = numpy.ndarray(shape=(self.num_ch,), dtype='float')
		# define a lock to guarantee atomic operations on the magnitudes-array
		self.mag_lock = threading.Lock()
		
		# define events to signal the completion of cycles between threads 
		self.ready = threading.Event()
		self.trigger = threading.Event()
		
		# keep track of the samples-per-second count
		self.sps = 0.
		
		# run the two loops each in its own thread
		self.read_thread = threading.Thread(None, self._readLoop, "DASReaderThread")
		self.trig_thread = threading.Thread(None, self._triggerLoop, "DASTriggerThread")
		self.run = False
		
		# build a list of device-file names
		self.dev = []
		for i in range(self.num_ch):
			self.dev.append("/dev/das08/ad0_%d" % i)
		
	
	def logMessage(self, msg):
		"""Write a message to the log-file-object
		"""
		try:
			self.logfd.write("DASReader: %s\n" % msg)
		except Exception, e:
			self.errMessage("Error writing to file '%s': %s" % (self.logfd.name, str(e)))
	
	def errMessage(self, msg):
		"""Write a message to the error-file-object
		"""
		try:
			self.errfd.write("DASReader: %s\n" % msg)
		except Exception, e:
			sys.stderr.write("Error writing to file '%s': %s\n" % (self.errfd.name, str(e)))
	
	def _read(self):
		"""Read one sample from each channel, in round-robin fashion, 'blocksize' times.
		i.e. Read one block of samples from all channels, interleaved.
		"""
		start_time = time.time()
		for i in range(self.blocksize):
			for ch in range(self.num_ch):
				fd = None
				try:
					# the DAS08 driver requires that each channel is opened before reading,
					# in order to control the 8-input multiplexer. The card only has ONE actual ADC.
					fd = open(self.dev[ch], 'rb', 0)
					bytes = fd.read(2)
				finally:
					if fd:
						fd.close()
				
				# store the read integer in the correct place in the buffer
				self.buf[ch, self.buf_ptr[ch]] = struct.unpack('<H', bytes)[0]
				# increment the write-pointer
				self.buf_ptr[ch] = (self.buf_ptr[ch] + 1) % self.bufsize
			
			# wait 10ms after reading 1 sample from all channels.
			# the aim is to get 100 sps on all channels.
			time.sleep(0.01)
				
		# calculate the sps rate
		self.sps = self.blocksize / (time.time() - start_time)
			
		
	def _readLoop(self):
		"""Loop forever, reading one block of samples from all channels,
		then calculate the pseudo-magnitude for each channel. Repeat
		"""
		while self.run:
			self._read()
				
			with self.mag_lock:
				for ch in range(self.num_ch):
					self.mag[ch] = self.buf[ch].std() / 100
				
			# siganl completion of one read-cycle
			self.ready.set()
				
	
	def start(self):
		"""Starts the Reader-thread and the Trigger-thread,
		but first pre-loads the input-buffer with valid data.
		"""
		# pre-fill buffer, before any calculations can take place
		for i in range(max(self.bufsize // self.blocksize, 1)):
			self._read()
		
		self.run = True
		self.read_thread.start()
		self.trig_thread.start()
		
	
	def stop(self):
		"""Stops the Reader-loop and the Trigger-loop.
		Waits for both threads to finish.
		"""
		self.run = False
		for t in (self.trig_thread, self.read_thread):
			if isinstance(t, threading.Thread) and t.isAlive():
				self.logMessage("Waiting for %s to finish..." % t.getName())
				t.join()
			
		self.logMessage("Done")
		
	
	def isReady(self):
		"""Returns 'True' if a read-cycle was completed, and no (other) thread is waiting for the next read-cycle to complete.
		"""
		return self.ready.isSet()
	
	def waitMag(self, timeout=None):
		"""Wait for a read-cycle to be completed. When this call returns, the pseudo-magnitudes will also have been calculated.
		"""
		self.ready.clear()
		self.ready.wait(timeout)
	
	def getMag(self):
		"""Returns the current array of pseudo-magnitudes
		"""
		with self.mag_lock:
			return self.mag
	
	def getSPS(self):
		"""Returns the current samples-per-second rate
		"""
		return self.sps
	
	def setThreshold(self, thresh):
		"""Set the trigger-threshold, in pseudo-magnitude units (0.0 < thresh <= 10.0)
		"""
		if thresh <= 0:
			raise ValueError("Threshold value must be > 0")
		
		self.threshold = thresh
	
	def _triggerLoop(self):
		"""MainLoop of the Trigger-thread
		Wait for the read-cycle to complete and pseudo-magnitudes to be calculated.
		Compare each channels'pseudo-magnitude with the current threshold.
		For each channel which isn't already triggered, and has a pseudo-magnitude > thresh,
		The duration is caluclated fro mthe magnitude, and the trigger-function is called with 
		the channel-number, the magnitude and the duration as arguments.
		Re-triggering of a triggered channel cannot occur for the calulated duration
		"""
		end = numpy.ndarray(shape=(self.num_ch,), dtype='float')
		end.fill(time.time())
		#end = [0] * self.num_ch
		while self.run:
			self.waitMag()
			mag = self.getMag()
			for ch in range(self.num_ch):
				now = time.time()
				if (now > end[ch]) and (mag[ch] > self.threshold):
					duration = 10**((mag[ch] + 1.05) / 2.22)
					end[ch] = now + 1 # duration
					
					self.trig_func(ch, mag[ch], duration)
					self.trigger.set()
				
			if (time.time() > end).all() and (mag < self.threshold).all():
				self.trigger.clear()
			
	def waitTrig(self, timeout=None):
		"""Waits for any channel to be triggered
		"""
		self.trigger.clear()
		self.trigger.wait(timeout)
	
	def hasTrigger(self):
		"""Returns 'True' if a channel has triggerd, and no (other) thread is waiting for the next trigger.
		"""
		return self.trigger.isSet()
	
	def trig_func(self, ch, mag, dur):
		"""A simple (example) trigger-function
		Prints 'Ch <c> triggered at mag= <m.mmm> for dur= <d.ddd> s"
		Alternative implementations must accept 3 arguments: (channel-number, magnitude, duration)
		"""
		self.logMessage("Ch %d triggered at mag= %.3f for dur= %.3f s" % (ch, mag, dur))
		
	def setTrigFunc(self, func):
		"""Register a trigger-function.
		Checks if the supplied argument is callable (ie. a method or function) and accepts the correct number of arguments.
		"""
		if hasattr(func, 'im_func'):
			if func.im_func.func_code.co_argcount != 4:
				raise AttributeError("Trigger callback function '%s' must take 4 arguments (self, channel, magnitude, duration)" % repr(func))
		elif hasattr(func, 'func_code'):
			if func.func_code.co_argcount != 3:
				raise AttributeError("Trigger callback function '%s' must take 3 arguments (channel, magnitude, duration)" % repr(func))
		else:
			raise TypeError("Trigger callback function '%s' is not callable" % repr(func))
		
		self.trig_func = func
	

if __name__ == '__main__':
	from optparse import OptionParser
	
	# Define default values
	default_channels = 2
	default_blksize = 4
	default_bufsize = 8
	default_thresh = 0.5
	default_xsize = 500
	
	op = OptionParser()
	
	# Define command-line options
	op.add_option("-v", "--verbose", action='store', type='string', dest='verbose', metavar='V',
					help="set verbosity (a bitmask) [default = 0]")
	op.add_option("-g", "--graph", action='store_true', dest='graph',
					help="draw a graph of the received signal using pylab")
	op.add_option("-x", "--xsize", action='store', type='int', dest='xsize', metavar='SIZE', 
					help="set X-axis length of the graph (implies -g) [default = %d]" % default_xsize)
	op.add_option("-c", "--channels", action='store', type='int', dest='channels', metavar='N',
					help="set number of channels to sample [default = %d]" % default_channels)
	op.add_option("-b", "--bufsize", action='store', type='int', dest='bufsize', metavar='SIZE',
					help="set size of sample buffer [default = %d]" % default_bufsize)
	op.add_option("-s", "--blocksize", action='store', type='int', dest='blocksize', metavar='SIZE',
					help="set size of sample block [default = %d]" % default_blksize)
	op.add_option("-t", "--threshold", action='store', type='float', dest='thresh', metavar='MAG',
					help="set trigger threshold magnitude [default = %.1f]" % default_thresh)
	
	# Set defaults
	op.set_defaults(graph=False)
	op.set_defaults(channels=default_channels)
	op.set_defaults(bufsize=default_bufsize)
	op.set_defaults(blocksize=default_blksize)
	op.set_defaults(thresh=default_thresh)
	
	# Parse command-line options
	(opts, args) = op.parse_args()
	
	# Parse 'verbosity' argument
	verbose = 0
	if opts.verbose != None:
		try:					# try binary first
			verbose = int(opts.verbose, 2)
		except ValueError:
			try:				# try decimal...
				verbose = int(opts.verbose)
			except ValueError:	# try hexadecimal
				x = opts.verbose.find('x')
				hex = opts.verbose[(x + 1):]
				try:
					verbose = int(hex, 16)
				except ValueError:
					sys.stderr.write("Invalid verbosity argument '%s'" % opts.verbose)

	# Instatntiate DASReader with the provided (or default) paramters
	dr = DASReader(opts.channels, opts.bufsize, opts.blocksize)
	
	# Set the threshold
	dr.setThreshold(opts.thresh)
	
	# Define a signal-handler for stopping the DASReader's threads
	def stophandler(sig, frame):
		dr.logMessage("Got signal %s" % sig)
		dr.stop()
	
	# Register signal-handler for Ctrl-C
	signal.signal(signal.SIGINT, stophandler)
	
	# Define an alternative trigger-function
	def trig_func(ch, mag, dur):
		print("Channel %d triggered at mag= %.3f for dur= %.3f" % (ch, mag, dur))
		
	# Register trigger-function
	dr.setTrigFunc(trig_func)
		
	# start the DASReader's threads
	dr.start()
	
	if opts.graph or opts.xsize:
		# use 'pylab' module to draw an animated line-graph of the channels' magnitudes
		try:
			import pylab as p
			
			# Set max nr of datapoints for the graph(s)
			if opts.xsize and (opts.xsize >= 50):
				xsize = opts.xsize
			else:
				xsize = default_xsize
				
			# Define initail datapoints at t = 0 as '0'
			tm = [0]
			mg = []
			for ch in range(dr.num_ch):
				mg.append([0])
			
			# draw the currently defined threshold as a dotted red line
			th = [dr.threshold]
			
			# put pylab in 'interactive mode'
			p.ion()
			
			# define a 'figure' (this creates the window for the grph(s))
			fig = p.figure(figsize=(1 + (xsize // 50), 1 + (2 * dr.num_ch)))
			
			# 'interactive mode' off
			p.ioff()
			
			# define the graph(s)
			graph = [[]] * dr.num_ch
			for ch in range(dr.num_ch):
				p.subplot(dr.num_ch, 1, ch + 1)
				graph[ch] = p.plot(tm, mg[ch], 'b-', th, 'r:')
				p.title('channel %d' %ch)
				p.ylabel('magnitude')
				
			# only label X-axis of the bottom graph
			p.xlabel('seconds')
			
			start_time = time.time()
			# run this loop until the dr is stopped
			while dr.run:
				# wait for magnitudes to be calculated
				dr.waitMag()
				mag = dr.getMag()
				
				# append current magnitudes to each list of datapoints
				for ch in range(dr.num_ch):
					mg[ch].append(mag[ch])
					if len(mg[ch]) > xsize:
						# discared oldest datapoint
						del mg[ch][0]
				
				# append elapsed time to list of time-points 
				tm.append(time.time() - start_time)
				if len(tm) > xsize:
					# discared oldest time-point
					del tm[0]
				
				# draw current threshold as a horizontal line
				th = [dr.threshold] * len(tm)
				
				for ch in range(dr.num_ch):
					graph[ch][0].set_data(tm, mg[ch])	# set new datapoints
					graph[ch][1].set_data(tm, th)		# set threshold points
				
					top = max(mg[ch])
					p.subplot(dr.num_ch, 1, ch + 1)
					# scale each graph's axes
					p.axis([tm[0], tm[-1], 0, max(top, 1)])
				
				p.draw()
				
				if (verbose & 1) != 0:
					print "%.1f s/s" % dr.getSPS()
				elif (verbose & 2) != 0:
					if dr.hasTrigger():
						star = '*'
					else:
						star = '-'
					
					sps = dr.getSPS()
					
					for ch in range(dr.num_ch):
						print "%s ch %d: mag=%6.3f (%5.1f s/s)" % (star, ch, mag[ch], sps)
				
		finally:
			dr.stop()
			try:
				p.close()
			except NameError:
				pass
			
			exit(0)
	

	try:
		top = 1
		# run this loop until dr is stopped, or an exception occurs
		while dr.run:
			# wait fro magnitudes to be calculated
			dr.waitMag()
			mag = dr.getMag()	# returns an numpy array..
			# calculate some integer values for drawing an 'ascii-art' 90-deg rotated graph
			top = max(int(mag.max() + 1), top)
			scale = top / 100.
			mg = mag // scale
			rm = 100 - mg
			
			if (verbose & 1) != 0:
				# only print the sps rate
				print "%.1f s/s" % dr.getSPS()
			elif (verbose & 2) != 0:
				# print the ascii-graph
				if dr.hasTrigger():
					star = '*'
				else:
					star = '-'
				
				sps = dr.getSPS()
					
				for ch in range(dr.num_ch):
					bar = '[' + (' ' * mg[ch]) + '|' + (' ' * rm[ch]) + ']'
					print "%s ch %d: mag=%6.3f (%5.1f s/s) %s %d" % (star, ch, mag[ch], sps, bar, top)
			
		
	finally:
		dr.stop()
	
	
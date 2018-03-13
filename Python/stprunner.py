#!/usr/bin/python
### _*_ coding: utf-8 _*_
#
# Parkfield Interventional Earth-Quake Fieldwork
#
# A set of classes for downloading seismograms using the STP protocol
# see http://www.data.scec.org/STP/stp.html
#
# This requires the pieqf-specific version of the 'stp v1.5' program to be installed.
# The C-sources for this program should be included in the SVN-repository where this file came from.
# After compiling ('make'), copy the 'stp' binary to /usr/local/bin, and copy the 'sample.stp' config-file to 
# /usr/local/bin/.stp or ~/.stp (it becomes a hidden file)
#
# The StpRunner class instantiates a QDMParser (see qdmparser.py) to keep a DB of recent seismic events.
# Whenever there are events in the DB for which a subdir in the defined outputdir does not yet exist,
# it starts an StpWrapper in its own thread, which in turn uses the 'stp' executable to query 
# the relevant seismic datacenter and to download seismograms for this event from the nearest few 
# seismographic stations, if such data exists.
# If no data exists (yet), the StpWrapper keeps retrying the events it is working on.
# In the meantime, the StpRunner might start other StpWrappers if more new events appear in the DB.
#
#	Stock, V2_Lab Rotterdam, June 2008
###
from __future__ import with_statement

import qdmparser

import datetime, time, types, os, stat, sys, subprocess, thread, threading
import numpy

###
# Global Variables
###

# possible seismogram formats
global out_fmts
out_fmts = ('SAC', 'SEED', 'MSEED', 'FLT32', 'INT32', 'ASCII', 'V0', 'COSMOS-V0', 'V1', 'COSMOS-V1')

# the seismic networks of interest, with the names of the STP server groups
global netgroup
netgroup = {'CI':'scedc', 'NC':'ncedc'}

###
# Global functions
###

def arstr(a, p=3) :
	"""Returns a string-representation of a numpy-array.
	
	This is simply a wrapper around numpy.array2string()
	"""
	return numpy.array2string(a, precision=p, suppress_small=True)

def veclen(a, axis=0) :
	"""Returns the length of a vector, or array of vectors
	
	This is simply a wrapper around numpy.ma.hypot.reduce()
	"""
	return numpy.ma.hypot.reduce(a, axis)

###
# Error class
###

class StpError(BaseException):
	def __init__(self, code, msg):
		self.code = code
		self.message = msg
		
	def __str__(self):
		out = ""
		if self.code != 0:
			out += "STP Error: "
		out += self.message
		if self.code != 0:
			out += " [exit-code %d]" % self.code
		
		return out

###
# STP wrapper class
###
		
			
class StpWrapper(object):
	"""This class contains methods to run the 'stp' program, send it commands, and parse its output.
	Multiple instances of this class, each running its own 'stp' subprocess, may exist.
	Any downloaded data is saved in a subfolder, named after the Event-ID, in the defined output-dir
	"""
	# Path of the 'stp' binary
	stpexec = "/usr/local/bin/stp"
	# Path of the seismograms dir-structure
	outputdir = "/var/lib/STP"
	
	# file-objects for writing informational messages, warnings & errors
	logfd = sys.stdout
	errfd = sys.stderr
	
	# a hierarchy of dicts for storing seismic networks' stations' locations
	stations = {'CI':{}, 'NC':{}}
	verbose = 0
	
	# Default values
	defaults = {'retryperiod':datetime.timedelta(1)}
	
	def __init__(self, name, qdm_parser=None, stations=None, defaults=None, outputdir=None):
		"""Instantiate an StpWrapper. The 'name' argument must be supplied, and should be unique.
		It is used as a prefix for reported/logged messages
		The other arguments are 'inherited' from the StpRunner that instantiates the StpWrapper(s)
		'qdmparser' should be the 'main' QDMParser instance. if not supplied, an(other) QDMParser is instantiated.
		'stations' should be a hierarchy of dicts containing the seismic networks' stations' locations.
			This information is initially retrieved from the networks' datacenters.
		'defaults' is a dict of 'parameter':<value> pairs. Relevant parameters are:
			'retryperiod' (a 'timedelta' object) the period of time to keep retring to get data for an Event.
		'outputdir' is the root-dir of the seismograms dir-structure.
		"""
		self.name = name
		
		if not (os.path.exists(self.stpexec) and os.access(self.stpexec, os.X_OK)):
			raise ValueError("STP Executable '%s' was not found or not executable" % self.stpexec)
		
		if isinstance(qdm_parser, qdmparser.QDMParser):
			self.qp = qdm_parser
		else:
			self.qp = qdmparser.QDMParser()
	
		self.stp = None
		self.net = None
		self.connected = None
		
		self.thread = None
		self.done = threading.Event()
		self.run = True
		
		# a list for storing rejected events
		self.rejects = []
		
		# copy provided stations-info
		if type(stations) == types.DictType:
			for net in netgroup.keys():
				if (net in stations) and (type(stations[net]) == types.DictType):
					self.stations[net] = stations[net]
				
		# copy provided defaults
		if type(defaults) == types.DictType:
			self.defaults.update(defaults)
			
		# check if provided outputdir exists
		if outputdir:
			if os.path.isdir(outputdir) and os.access(outputdir, os.W_OK):
				self.outputdir = outputdir
			else:
				raise OSError("Specified output-dir '%s' was not found or not writable" % outputdir)

	def logMessage(self, msg):
		"""Write a message, prefixed by the STP-process name, to the log-file-object
		"""
		try:
			self.logfd.write("%s: %s\n" % (self.name, msg))
		except Exception, e:
			self.errMessage("Error writing to file '%s': %s" % (self.logfd.name, str(e)))
	
	def errMessage(self, msg):
		"""Write a message, prefixed by the STP-process name, to the error-file-object
		"""
		try:
			self.errfd.write("%s: %s\n" % (self.name, msg))
		except Exception, e:
			sys.stderr.write("Error writing to file '%s': %s\n" % (self.errfd.name, str(e)))
	
	
	def _readstp(self):
		"""Read line(s) of text output by the running 'stp' process
		Check the 'stp' process' returncode, when it exits, and take appropriate action
		(May raise StpError)
		"""
		while self.stp.poll() == None:
			line = self.stp.stdout.readline()
				
			line = line.strip('\n')
			
			if not len(line):
				continue
			
			if (self.verbose & 1) != 0:
				self.logMessage("STP: %s" % line)
				
			if line.startswith('STP>'):
				continue
				
			break
		
		else:
			self.net = None
			self.connected = None
			if self.stp.returncode in (-1, -2, -3, -4, -5, -6, -9, -14, -15):	# got signal
				self.logMessage("STP: Interrupted (%d)" % self.stp.returncode)
				return None
			elif self.stp.returncode == -11:	# SEGV
				raise StpError(-11, "Segfault in %s" % os.path.basename(self.stpexec))
			elif self.stp.returncode == -8:	# No configfile found
				thread.interrupt_main()
				raise StpError(-8, "Config-file '~/.stp' or '%s/.stp' not found" % os.path.dirname(self.stpexec))
			else:
				raise StpError(self.stp.returncode, "Disconnected")
			
		return line
	
	
	def connect(self, net):
		"""Start an 'stp' subprocess, connecting to the provided network's STP server group.
		When connected, may set various STP parameters according to parameters found in StpWrapper.defaults:
		'verbose' (any value) set verbose mode in the 'stp' program
		'format' (one of the strings in out_fmts) set downloaded seismograms' file-format
		'gaincorr' (True / False) set seismogram gain-correction on / off
		(May raise StpError)
		"""
		if not net in netgroup:
			raise StpError(4, "Unrecognized netcode: '%s'" % str(net))
		
		if (self.stp != None) and (self.stp.returncode == None):
			raise StpError(2, "Already connected")
		
		args = [self.stpexec, "-d", self.outputdir, netgroup[net]]
		self.stp = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
	
		line = ""
		while self.run and (line != None):
			line = self._readstp()
			
			if line == 'Done':
				break
		
		else:
			return
		
		self.net = net
		self.connected = datetime.datetime.utcnow()
		self.avail = {}
		
		if 'verbose' in self.defaults:
			self.toggleVerbose()
	
		if 'format' in self.defaults:
			self.setFormat(self.defaults['format'])
	
		if 'gaincorr' in self.defaults:
			self.setGainCorr(self.defaults['gaincorr'])
	
	
	def disconnect(self):
		"""Disconnect (ie. exit) the 'stp' subprocess
		"""
		if (self.stp == None) or (self.stp.returncode != None):
			return
			
		cmd = 'EXIT'
		try:
			self.stp.stdin.write("%s\n" % cmd)
		except IOError:		# 'Broken pipe' i.e. stp-subprocess was already killed
			return

		line = ""
		while line != None:
			try:
				line = self._readstp()
			except IOError:
				break
			except StpError, e:
				self.logMessage(str(e))
				break
		
		self.connected = None
		
		
		
	def getStations(self):
		"""Request (and parse) a list of stations for the network we're connected to
		(May raise StpError)
		"""
		if (self.stp == None) or (self.stp.returncode != None):
			raise StpError(1, "Not connected")
			
		cmd = 'STA -l'
		self.stp.stdin.write("%s\n" % cmd)
	
		stations = {}
	
		count = 0
		while self.run:
			line = self._readstp()
			
			if (line == 'Done') or (line == None):
				break
			
			tokens = line.split()
			if tokens[0] == '#':
				try:
					count = int(tokens[-1])
				except ValueError, e:
					raise StpError(8, "Non-int value in '# Number of stations' message: %s" % tokens[-1])
			
			else:
				station = tokens[0]
				data = []
				for val in tokens[1:3]:
					try:
						data.append(float(val))
					except ValueError, e:
						raise StpError(8, "Non-float value in station '%s' data: %s" % (station, val))
					
				stations[station] = data
	
		self.stations[self.net].update(stations)
		if count != len(stations):
			self.errMessage("Warning: Number of available stations (%d) does not match station-count (%d)" % (count, len(stations)))
		
		return len(stations)
	
	def _parseTime(self, time_string):
		"""Parse a time & date string as present in the 'stp' output
		returns the time in Python format (floating-point seconds-since-the-epoch)
		"""
		ts = time_string.split('.')
		tt = time.strptime(ts[0], "%Y/%m/%d,%H:%M:%S")
		tf = int(ts[1]) / 1000.
		return (time.mktime(tt) + tf)
		
	
	def _parseDuration(self, duration_string):
		"""Parse a duration string as present in the 'stp' output
		returns the duartion in Python format (floating-point seconds)
		(May raise StpError)
		"""
		du = duration_string[-1]
		if du == 's':
			d = float(duration_string[:-1])
		elif du == 'm':
			d = float(duration_string[:-1]) * 60.
		else:
			raise StpError(8, "Unknown time-unit in duration value '%s'" % time_strings[1])
		
		return d
		
	
	def getEvent(self, event_in):
		"""Request (and parse) data on one event (dict)
		returns a dict containing the event metadata as provided by the datacenter
		(May raise StpError)
		"""
		if (self.stp == None) or (self.stp.returncode != None):
			raise StpError(1, "Not connected")
			
		if (type(event_in) != types.DictType) or ('id' not in event_in):
			raise StpError(7, "Invalid event '%s'" % str(event_in))
		
		cmd = 'EVENT -e %s' % str(event_in['id'])
		self.stp.stdin.write("%s\n" % cmd)
	
		event_out = {}
		count = 0
		while self.run:
			line = self._readstp()
			
			if (line == 'Done') or (line == None):
				break
			
			tokens = line.split()
			if tokens[0] == '#':
				try:
					count = int(tokens[-1])
				except ValueError, e:
					raise StpError(8, "Non-int value in '# Number of events' message: %s" % tokens[-1])
			
			elif tokens[1] == 'No':
				continue
			
			else:
				event_out['net'] = self.net
				event_out['id'] = tokens[0]
				event_out['type'] = tokens[1]
				event_out['time'] = self._parseTime(tokens[2])
				event_out['loc'] = []
				for val in tokens[3:5]:
					try:
						event_out['loc'].append(float(val))
					except ValueError, e:
						raise StpError(8, "Non-float value in event '%s' location: %s" % (tokens[0], val))
				try:	
					event_out['depth'] = float(tokens[5])
				except ValueError, e:
					raise StpError(8, "Non-float value in event '%s' depth: %s" % (tokens[0], tokens[6]))
				try:	
					event_out['mag'] = float(tokens[6])
				except ValueError, e:
					raise StpError(8, "Non-float value in event '%s' magnitude: %s" % (tokens[0], tokens[6]))
				event_out['magtype'] = tokens[7]
				try:	
					event_out['qual'] = float(tokens[8])
				except ValueError, e:
					raise StpError(8, "Non-float value in event '%s' quality: %s" % (tokens[0], tokens[8]))
				
		if len(event_out) and (count != 1):
			self.errMessage("Warning: Number of available events (%d) does not match count (1)" % count)
		
		return event_out
	
	
	def getEvents(self, events_in):
		"""Request (and parse) data on multiple events (a list of dicts)
		returns a list of dicts containing the events' metadata as provided by the datacenter
		(May raise StpError)
		"""
		if (self.stp == None) or (self.stp.returncode != None):
			raise StpError(1, "Not connected")
			
		if type(events_in) != types.ListType:
			events_in = [events_in]
		
		cmd = 'EVENT -e'
		for ev in events_in:
			if (type(ev) != types.DictType) or ('id' not in ev):
				raise StpError(7, "Invalid event '%s'" % str(ev))
			
			cmd += ' %s' % str(ev['id'])
			
		self.stp.stdin.write("%s\n" % cmd)
	
		events_out = {}
		count = 0
		while self.run:
			line = self._readstp()
			
			if (line == 'Done') or (line == None):
				break
			
			tokens = line.split()
			if tokens[0] == '#':
				try:
					count = int(tokens[-1])
				except ValueError, e:
					raise StpError(8, "Non-int value in '# Number of events' message: %s" % tokens[-1])
			
			elif tokens[1] == 'No':
				continue
			
			else:
				event = {'net':self.net, 'id': tokens[0]}
				event['type'] = tokens[1]
				event['time'] = self._parseTime(tokens[2])
				event['loc'] = []
				for val in tokens[3:5]:
					try:
						event['loc'].append(float(val))
					except ValueError, e:
						raise StpError(8, "Non-float value in event '%s' location: %s" % (tokens[0], val))
				try:	
					event['depth'] = float(tokens[5])
				except ValueError, e:
					raise StpError(8, "Non-float value in event '%s' depth: %s" % (tokens[0], tokens[6]))
				try:	
					event['mag'] = float(tokens[6])
				except ValueError, e:
					raise StpError(8, "Non-float value in event '%s' magnitude: %s" % (tokens[0], tokens[6]))
				event['magtype'] = tokens[7]
				try:	
					event['qual'] = float(tokens[8])
				except ValueError, e:
					raise StpError(8, "Non-float value in event '%s' quality: %s" % (tokens[0], tokens[8]))
				
				events_out[event['id']] = event
		
		if len(events_out) and (count != len(events_out)):
			self.errMessage("Warning: Number of available events (%d) does not match count (%d)" % (count, len(self.events)))
		
		return events_out.values()
	
	
	def getAvail(self, event, channels='H%'):
		"""Request a list of available seismograms for the given event, on the provided channels
		'event' is a dict with Event metadata
		'channels' can be a string or a list of strings containg (a) three-letter channel-code(s),
		or (a) channel-code(s) containing the '%' or '_' wildcards (see the STP manual)
		(May raise StpError)
		"""
		if (self.stp == None) or (self.stp.returncode != None):
			raise StpError(1, "Not connected")
			
		if (type(event) != types.DictType) or ('id' not in event):
			raise StpError(7, "Invalid event '%s'" % str(event))
		
		if type(channels) != types.ListType:
			channels = [channels]
		
		count = 0
		for chan in channels:
			if (type(chan) not in types.StringTypes) or (len(chan) > 3)  or ((len(chan) < 3) and '%' not in chan):
				raise StpError(6, "Invalid channel '%s'" % str(chan))
			if (len(chan) == 3) and ((chan[1] not in ('H', 'L', '_', '%')) or (chan[2] not in ('E', 'N', 'Z', '2', '3', '_', '%'))):
				raise StpError(6, "Invalid channel '%s'" % str(chan))
		
			cmd = 'EAVAIL -l -chan %s %s' % (chan, event['id'])
			self.stp.stdin.write("%s\n" % cmd)
		
			while self.run:
				line = self._readstp()
				
				if (line == 'Done') or (line == None):
					break
				
				tokens = line.split()
				if tokens[0] == '#':
					try:
						count += int(tokens[-1])
					except ValueError, e:
						raise StpError(8, "Non-int value in '# of seismograms' message: %s" % tokens[-1])
				
				else:
					station = "%s.%s" % (tokens[0], tokens[1])
					wave = {'chan':tokens[2]}
					if tokens[3] not in ('T', 'C'):
						wave['loc'] = tokens.pop(3)	# location-code
						
					wave['time'] = self._parseTime(tokens[-2])
					wave['dur'] = self._parseDuration(tokens[-1])
					if station in self.avail:
						self.avail[station].append(wave)
					else:
						self.avail[station] = [wave]
		
		cnt = 0
		for l in self.avail.values():
			cnt += len(l)
		
		if count != cnt:
			self.errMessage("Warning: Number of available seismograms (%d) does not match count (%d)" % (count, cnt))
		
		return cnt
	
	
	def getClosest(self, event, num=1, channels='H%'):
		"""Returns a list of station-identifiers for the 'num' station(s), that have
		data available for the given event, closest to the given event.
		'event' is a dict with Event metadata
		'num' is an integer >= 1
		'channels' can be a string or a list of strings containg (a) three-letter channel-code(s),
		or (a) channel-code(s) containing the '%' or '_' wildcards (see the STP manual)
		(May raise StpError)
		"""
		if (self.stp == None) or (self.stp.returncode != None):
			raise StpError(1, "Not connected")
		
		if not len(self.avail):
			self.getAvail(event, channels)
		if not len(self.avail):
			return []
		
		stations = {}
		for sta in self.avail.keys():
			if sta not in self.stations[self.net]:
				if len(self.stations[self.net]):
					self.errMessage("Warning: Unknown station '%s'. re-fetching stations-list." % sta)
					
				self.getStations()
				if sta not in self.stations[self.net]:
					raise StpError(5, "Unknown station '%s'" % sta)
				
			stations[sta] = self.stations[self.net][sta]
		
		if num > len(stations):
			num = len(stations)
		
		positions = numpy.array(stations.values())
		codes = numpy.array(stations.keys())
		distances = veclen(positions - numpy.array(event['loc']), axis=1)
		
		idxes = distances.argsort()
		
		if (self.verbose & 8) != 0:
			self.logMessage("Distances:\n%s" % arstr(distances.take(idxes)))
		
		closest = codes.take(idxes)
		
		return closest[:num].tolist()
		
	
	def getSeismograms(self, events, stations, channels='H%'):
		"""Request to download seismograms for the given event, from the given stations, on the given channels.
		'event' is a dict with Event metadata
		'stations' is a list of station-identifiers (strings)
		'channels' can be a string or a list of strings containg (a) three-letter channel-code(s),
		or (a) channel-code(s) containing the '%' or '_' wildcards (see the STP manual)
		(May raise StpError)
		"""
		if (self.stp == None) or (self.stp.returncode != None):
			raise StpError(1, "Not connected")
		
		if type(events) != types.ListType:
			events = [events]
		
		if type(channels) != types.ListType:
			channels = [channels]
		
		if type(stations) != types.ListType:
			stations = [stations]
		
		ev_str = ""
		for ev in events:
			if (type(ev) != types.DictType) or ('id' not in ev):
				raise StpError(7, "Invalid event '%s'" % str(ev))
			
			ev_str += " %s" % str(ev['id'])
				
		for station in stations:
			if (type(station) not in types.StringTypes) or ('.' not in station):
				raise StpError(5, "Invalid station '%s'" % str(station))
			
			net, sta = station.split('.')
			
			for chan in channels:
				if (type(chan) not in types.StringTypes) or (len(chan) > 3)  or ((len(chan) < 3) and '%' not in chan):
					raise StpError(6, "Invalid channel '%s'" % str(chan))
				if (len(chan) == 3) and ((chan[1] not in ('H', 'L', '_', '%')) or (chan[2] not in ('E', 'N', 'Z', '2', '3', '_', '%'))):
					raise StpError(6, "Invalid channel '%s'" % str(chan))
			
				cmd = "TRIG -net %s -sta %s -chan %s %s" % (net, sta, chan, ev_str)
				self.stp.stdin.write("%s\n" % cmd)
				
				line = ""
				while self.run and (line != None):
					line = self._readstp()
					
					if line == 'Done':
						break
					
				else:
					return {}
		
		# count the seismograms
		cnt = {}
		for ev_id in ev_str.split():
			ev_dir = os.path.join(self.outputdir, ev_id)
			if os.path.isdir(ev_dir):
				cnt[ev_id] = max(0, len(os.listdir(ev_dir)) - 1) # don't count the <ev_id>.event file
		
		return cnt
		
		
	def getStatus(self):
		"""Request (and parse) the STP client and server status
		Returns a dict with 'name':<value> pairs
		(May raise StpError)
		"""
		if (self.stp == None) or (self.stp.returncode != None):
			raise StpError(1, "Not connected")
		
		self.stp.stdin.write("STATUS\n")
		
		status = {}
		while self.run:
			line = self._readstp()
			
			if (line == 'Done') or (line == None):
				break
			
			i = line.find('=')
			if i < 0:
				continue
			
			key = line[:i].strip()
			val = line[i+1:].strip()
			
			status[key] = val
			
		return status
	
		
	def toggleVerbose(self):
		"""Toggle the STP client's verbose mode on / off
		(May raise StpError)
		"""
		if (self.stp == None) or (self.stp.returncode != None):
			raise StpError(1, "Not connected")
		
		self.stp.stdin.write("VERBOSE\n")
		
		ret = None
		while self.run:
			line = self._readstp()
			
			if (line == 'Done') or (line == None):
				break
			
			tokens = line.split()
			if tokens[0] == 'verbose':
				if tokens[-1] == 'on':
					ret = True
				else:
					ret = False
		
		return ret
			
			
	def setGainCorr(self, corr=True):
		"""Enable or disable the gain-correction for downloaded seismograms
		Returns 'True' (if enabled) or 'False' (if disabled)
		(May raise StpError)
		"""
		if (self.stp == None) or (self.stp.returncode != None):
			raise StpError(1, "Not connected")
		
		if corr:
			cmd = 'GAIN ON'
		else:
			cmd = 'GAIN OFF'
		
		self.stp.stdin.write("%s\n" % cmd)
		
		ret = None
		while self.run:
			line = self._readstp()
			
			if (line == 'Done') or (line == None):
				break
			
			tokens = line.split()
			if tokens[0] == 'Correcting':
				ret = True
			elif tokens[0] == 'No':
				ret = False
			
		return ret
			
	
	def setFormat(self, format):
		"""Set the file-format for downlaoded seismograms.
		The requested 'format' must be one of the strings in the out_fmts global variable
		Returns the currently set output-format (string)
		(May raise StpError)
		"""
		if (self.stp == None) or (self.stp.returncode != None):
			raise StpError(1, "Not connected")
		
		if type(format) in types.StringTypes:
			uformat = str(format).upper()
			if uformat in out_fmts:
				format = uformat
			else:
				raise StpError(9, "Unrecognized output-format '%s'" % format)
		elif (type(format) == types.IntType) and (format >= 0) and (format < len(out_fmts)):
			format = out_fmts[format]
		else:
			raise StpError(9, "Invalid output-format '%s'" % str(format))
			
		self.stp.stdin.write("%s\n" % format)
		
		line = ""
		while self.run and (line != None):
			line = self._readstp()
			
			if line == 'Done':
				break
			
		return self.getStatus()['Format']
	
	def _rmDir(self, ev):
		"""Remove an empty event-dir from the outputdir tree
		"""
		ev_dir = os.path.join(self.outputdir, ev['id'])
		try:	# try to remove event's dir
			ls = os.listdir(ev_dir)
			if (len(ls) == 1) and ls[0].endswith('.evnt'):
				os.remove(os.path.join(ev_dir, ls[0]))
			os.rmdir(ev_dir)
		except OSError:		# dir not empty
			pass
	
	def _tdString(self, td):
		"""Return a string describing the value of a datetime.timedelta as
		'nd, nh, nm, ns' or any subset thereof.
		"""
		out = ""
		if td.days > 0:
			out += "%dd, " % td.days
		hours = td.seconds // 3600
		if hours > 0:
			out += "%dh, " % hours
		minutes = (td.seconds // 60) % 60
		if minutes > 0:
			out += "%dm, " % minutes
		seconds = td.seconds % 60
		if seconds > 0:
			out += "%ds, " % seconds
		return out[:-2]
	
	def _idStr(self, ev):
		"""Returns the event's network-code and event-ID as one string.
		The netcode and ID are simoly cincatenated with a ':' in between.
		"""
		return "%s:%s" % (ev['net'], ev['id'])
	
	def _locStr(self, loc):
		"""Returns a geographic location (a (latitude, longitude) tuple)
		as a string
		"""
		if loc[0] >= 0:
			lat = '%.3f°N' % loc[0]
		else:
			lat = '%.3f°S' % -loc[0]
		if loc[1] >= 0:
			lon = '%.3f°E' % loc[1]
		else:
			lon = '%.3f°W' % -loc[1]
			
		return "%s,%s" % (lat, lon)
	
	def _eventStr(self, ev):
		"""Returns the event's metadata as a string
		"""
		timestring = time.strftime("%b %d %Y - %H:%M:%S UTC", time.localtime(ev['time']))
		out = "%s on %s, mag %.1f" % (self._idStr(ev), timestring, ev['mag'])
		if 'magtype' in ev:
			out += " (%s)" % ev['magtype']
		if 'type' in ev:
			out += ", type '%s'" % ev['type']
		out += ", at %s" % self._locStr(ev['loc'])
		if 'depth' in ev:
			out += ", %.1f km deep" % ev['depth']
		if 'dmin' in ev:
			out += ", %.1f km from nearest station" % ev['dmin']
		if 'qual' in ev:
			out += ", quality %.1f" % ev['qual']
	
		return out
	
	def runStp(self, events, stn_count=3, channels='H%'):
		"""The main seismogram retreival cycle.
		Tries to run connect(ev['net']), getEvent(ev), getClosest(ev, stn_count, channels)
		and getSeismograms(ev, closest_stations, channels) for each event in 'events'
		If any of these steps yeild no data, the event in question is delegated to a 'retry'
		list. If the events-list is empty but the retry-list is not, wait a pre-defined period
		(either 30 sec or 5 min, depending on which step failed) and run the whole sequence again
		with the events in the retry-list.
		May reject events depending on event-type (man-made events are rejected) or magnitudes <= 0
		Will give up on events after the StpWrapper.defaults['retryperiod'] expires
		(May raise StpError)
		"""
		if self.stp != None:
			raise StpError(3, "%s Already running. Connected to '%s'" % (self.name, self.net))
		
		if type(events) != types.ListType:
			events = [events]
		
		ev_str = ""
		for ev in events:
			ev_str += "%s, " % self._idStr(ev)
			
		starttime = datetime.datetime.utcnow()
		endtime = starttime + self.defaults['retryperiod']
		timestring = starttime.strftime("%b %d %Y - %H:%M:%S UTC")
		self.logMessage("Started at %s with events [%s]" % (timestring, ev_str[:-2]))
		
		self.run = True
		self.done.clear()
		self.downloaded = {}
		while self.run:
			retry = []
			while len(events):
				if not self.run:
					self.disconnect()
					break
				
				ev = events.pop(0)
				
				if (type(ev) != types.DictType) or ('id' not in ev) or ('net' not in ev):
					raise StpError(7, "Invalid event '%s'" % str(ev))
				
				if ev['net'] != self.net:
					self.disconnect()
				
					try:
						self.connect(ev['net'])
					except StpError, e:
						self.logMessage("Failed to connect: %s. Will retry in 30 sec" % str(e))
						retry.append(ev)
						delay = 30
						continue
				
				ev_out = self.getEvent(ev)
				
				if len(ev_out) == 0:
					self.logMessage("%s datacenter has no data for event %s (yet). Will retry in 5 min" % (ev['net'], self._idStr(ev)))
					retry.append(ev)
					delay = 300
					continue
				
				elif ev_out['type'] not in ('le', 're', 'ts'):
					self.logMessage("Event %s is not an earthquake; type = '%s'" % (self._idStr(ev_out), ev_out['type']))
					ev['reason'] = "man-made event type: %s" % ev_out['type']
					self.rejects.append(ev)
					continue
				
				if 'retry' not in ev:
					self.logMessage("Event %s" % self._eventStr(ev_out))
				
				cl = self.getClosest(ev_out, stn_count, channels)
				if len(cl) == 0:
					self.logMessage("No stations have data for event %s (yet). Will retry in 5 min" % self._idStr(ev_out))
					retry.append(ev)
					delay = 300
					continue
				
				ret = self.getSeismograms(ev_out, cl, channels)
				if (ev_out['id'] not in ret) or (ret[ev_out['id']] == 0):
					self.logMessage("No seismograms available for event %s (yet). Will retry in 5 min" % self._idStr(ev_out))
					self._rmDir(ev_out)
					retry.append(ev)
					delay = 300
					continue
				
				self.downloaded.update(ret)
				timestring = self._tdString(datetime.datetime.utcnow() - datetime.datetime.fromtimestamp(ev_out['time']))
				self.logMessage("Downloaded %d seismograms for event %s from %d stations, %s after the event" % (ret[ev_out['id']], self._idStr(ev_out), len(cl), timestring))
			
			else:	# the 'else' of the inner 'while' loop. i.e. if len(events) == 0
				self.disconnect()
				
				if not len(retry):
					break	# break the outer 'while' loop
					
				if (datetime.datetime.utcnow() < endtime):
					tick = 0
					while (tick < delay) and self.run:
						tick += 1
						time.sleep(1)
					
					events = []
					current = self.qp.getAllIds()
					ev_str = ""
					for ev in retry:
						if ev['id'] not in current:
							ev_str += "%s, " % self._idStr(ev)
							continue
						
						ev['retry'] = True
						events.append(ev)
						
					if len(ev_str):
						timestring = datetime.datetime.utcnow().strftime("%b %d %Y - %H:%M:%S UTC")
						self.logMessage("Events [%s] no longer in DB at %s" % (ev_str[:-2], timestring))
					
					if not len(events):
						break	# break the outer 'while' loop
					
					continue
				
				ev_str = ""
				for ev in retry:
					ev['reason'] = "timed out"
					self.rejects.append(ev)
					ev_str += "%s, " % self._idStr(ev)
					
				timestring = endtime.strftime("%b %d %Y - %H:%M:%S UTC")
				self.logMessage("Retry-period expired at %s. Giving up on events [%s]" % (timestring, ev_str[:-2]))
				break	# break the outer 'while' loop
				
		self.done.set()
		self.logMessage("Done at %s" % datetime.datetime.utcnow().strftime("%b %d %Y - %H:%M:%S UTC"))
						
	
	def isDone(self):
		"""Returns 'True' if the runStp() call has been completed
		"""
		return self.done.isSet()
	
	def start(self, events, stn_count=3, channels='H%'):
		"""Starts the runStp() method in a new thread.
		(May raise StpError)
		"""
		if self.thread and self.thread.isAlive():
			raise StpError(3, "%s Already started" % self.name)
			
		self.thread = threading.Thread(None, self.runStp, "%sthread" % self.name, [events, stn_count, channels])
		self.thread.start()
		
	def stop(self):
		"""Stops a running runStp()-process and waits for its thread to finish
		"""
		self.run = False
		self.logMessage("Stopping")
		if self.thread and self.thread.isAlive():
			self.logMessage("Waiting for %s to finish..." % self.thread.getName())
			self.thread.join()
		

class StpRunner(object):
	"""Compares the list of events returned by QDMParser.getAll() against the existing subdirs with seismograms in its output-dir
	and creates and runs an StpWrapper for each (set of) events that do not yet have downloaded seismograms
	"""
	# Path of the seismograms dir-structure
	outputdir = "/var/lib/STP"
	
	# a hierarchy of dicts for storing seismic networks' stations' locations
	stations = {'CI':{}, 'NC':{}}
	verbose = 0
	
	# Default values
	defaults = {'retryperiod':datetime.timedelta(1),
				'retainperiod':datetime.timedelta(30)}
	
	# a list of running StpWrappers
	sws = []
	# a dict of events in process, associated with the StpWrapper that is processing them
	proc = {}
	
	mainthread = None
	run = True
	
	# a seperate thread for the 'GarbageCollector'
	gcthread = None
	gcrun = False
	
	# default max number of StpWrapper-threads to start
	maxthreads = 10
	
	def __init__(self, qdm_parser=None, stations=None, logfile=None, errfile=None, outputdir=None):
		"""Instantiate an StpRunner
		'qdmparser' should be a QDMParser instance, or 'None' in which case a QDMParser is instantiated
		'stations' should be a hierarchy of dicts containing the seismic networks' stations' locations.
			if not ptovided, the default (empty) stations dict will be used and this will be populated by the first
			StpWrapper run for each network
		'logfile' and 'errfile' should be filenames defining where to log informational- and error-messages.
		if not provided, sys.stdout and sys.stderr will be used
		'outputdir' is the root-dir of the seismograms directory-tree. (/var/lib/STP/ per default)
		"""
		if isinstance(qdm_parser, qdmparser.QDMParser):
			self.qp = qdm_parser
		else:
			# create a QDMParser instance
			self.qp = qdmparser.QDMParser()
	
		self.errfd = None
		if errfile:
			# create and open the error logging file
			errdir = os.path.dirname(errfile)
			if errdir == '':
				errdir = './'
			if os.path.basename(errfile) == '':
				errfile = os.path.join(errdir, 'stprunner.err')
			else:
				errfile = os.path.join(errdir, os.path.basename(errfile))
			if not os.path.isdir(errdir):
				try:
					os.makedirs(errdir)
				except OSError, e:
					sys.stderr.write("Unable to create errorfile dir '%s': %s\n" % (errdir, str(e)))
					
			try:
				self.errfd = open(errfile, 'a', 1)	# append to file, line-buffered file
			except IOError, e:
				sys.stderr.write("Unable to create errorfile '%s': %s\n" % (errfile, str(e)))
		
		if self.errfd == None:
			# ... or use sys.stderr
			self.errfd = sys.stderr
			
		self.logfd = None
		if logfile:
			# create and open the logfile
			if (logfile == errfile) and (self.errfd != sys.stderr):
				self.logfd = self.errfd
			else:
				logdir = os.path.dirname(errfile)
				if logdir == '':
					logdir = './'
				if os.path.basename(logfile) == '':
					logfile = os.path.join(logdir, 'stprunner.log')
				else:
					logfile = os.path.join(logdir, os.path.basename(logfile))
				if not os.path.isdir(logdir):
					try:
						os.makedirs(logdir)
					except OSError, e:
						self.errMessage("Unable to create logfile dir '%s': %s" % (logdir, str(e)))
						
				try:
					self.logfd = open(logfile, 'a', 1)	# append to file, line-buffered file
				except IOError, e:
					self.errMessage("Unable to create logfile '%s': %s" % (logfile, str(e)))
		
		if self.logfd == None:
			# ... or use sys.stdout
			self.logfd = sys.stdout
					
		if outputdir:
			self.outputdir = outputdir

		if not (os.path.isdir(self.outputdir) and os.access(self.outputdir, os.W_OK)):
			# create outputdir if it doesn't exist
			os.makedirs(self.outputdir)
		
		if type(stations) == types.DictType:
			# copy provided stations
			for net in netgroup.keys():
				if (net in stations) and (type(stations[net]) == types.DictType):
					self.stations[net] = stations[net]
				
		# a lock for guaranteeing atomic manipulations of the list of StpWrappers
		self.sws_lock = threading.Lock()
		
		# keep track of the number of known stations on each network
		self.stn_count = {}
		for net in netgroup.keys():
			self.stn_count[net] = len(self.stations[net])
					
	def logMessage(self, msg):
		"""Write a message, prefixed by 'STPRunner: " to the log-file-object
		"""
		try:
			self.logfd.write("STPRunner: %s\n" % msg)
		except Exception, e:
			self.errMessage("Error writing to file '%s': %s" % (self.logfd.name, str(e)))
	
	def errMessage(self, msg):
		"""Write a message, prefixed by 'STPRunner: " to the err-file-object
		"""
		try:
			self.errfd.write("STPRunner: %s\n" % msg)
		except Exception, e:
			sys.stderr.write("Error writing to file '%s': %s\n" % (self.errfd.name, str(e)))
	
	
	def setVerbose(self, verbose):
		"""Set the verbosity level. This is a mask of bits, where each set bit causes certain
		data to be written to the logfile (or stdout, if no logfile is defined):
		bit 0 (  1): write the output from the 'stp' subprocesses
		bit 1 (  2): set the 'stp' processes to verbose mode (see StpWrapper.connect())
				(this is useless without bit 0 also being set...)
		bit 2 (  4): write the number of known stations per network, whenever it changes
		bit 3 (  8): write the array of event-to-station distances (see StpWrapper.getClosest())
		bit 4 ( 16): write the dict of events being processed whenever it changes
		bit 5 ( 32): write the list of 'blacklisted' event-IDs upon reload
		bit 6 ( 64): write the list of event-IDs currently in the DB upon reload
		The 'verbose' value given is the sum (bitwise OR) of the desired bits' values
		"""
		self.verbose = (verbose & ~2)
		if (verbose & 2) != 0:
			self.defaults['verbose'] = True
		elif 'verbose' in self.defaults:
			del self.defaults['verbose']

	def setFormat(self, format):
		"""Set the file-format for seismograms downloaded by future StpWrappers.
		The requested 'format' must be one of the strings in the out_fmts global variable
		"""
		if format != None:
			self.defaults['format'] = format
		elif 'format' in self.defaults:
			del self.defaults['format']

	def setGainCorr(self, gaincorr):
		"""Enable or disble the gaincorrection for seismograms downloaded by future StpWrappers
		"""
		if gaincorr:
			self.defaults['gaincorr'] = True
		elif 'gaincorr' in self.defaults:
			del self.defaults['gaincorr']

	def _parsePeriod(self, period):
		"""Parse a time-preiod spec (string) and return a datetime.timedelta object
		"""
		try:
			td = float(period)
			return datetime.timedelta(td)
		except ValueError:
			try:
				tu = period[-1].lower()
				td = float(period[:-1])
			except ValueError:
				raise ValueError("Invalid time-period spec: %s" % str(period))
			except AttributeError:
				raise ValueError("Invalid time-period spec: %s" % str(period))
			
			if tu == 'd':
				return datetime.timedelta(td)
			if tu == 's':
				return datetime.timedelta(0, td)
			if tu == 'm':
				return datetime.timedelta(0, 0, 0, 0, td)
			if tu == 'h':
				return datetime.timedelta(0, 0, 0, 0, 0, td)
			if tu == 'w':
				return datetime.timedelta(0, 0, 0, 0, 0, 0, td)
			else:
				raise ValueError("Invalid time-period spec: %s" % str(period))
	
	def setRetryPeriod(self, period):
		"""Set the 'keep retrying' timeout period for future StpWrappers
		'period' is a string containing a (floating-point) number, optionally followed
		by one of 's', 'm', 'h', 'd' or 'w' (if no letter present, 'd' for days is assumed)
		"""
		self.defaults['retryperiod'] = self._parsePeriod(period)
				
	def setRetainPeriod(self, period):
		"""Set the period of time to retain downloaded seismograms for events that
		no longer appear in the current DB
		'period' is a string containing a (floating-point) number, optionally followed
		by one of 's', 'm', 'h', 'd' or 'w' (if no letter present, 'd' for days is assumed)
		"""
		self.defaults['retainperiod'] = self._parsePeriod(period)

	def _tdString(self, td):
		"""Return a string describing the value of a datetime.timedelta as
		'nd, nh, nm, ns' or any subset thereof.
		"""
		out = ""
		if td.days > 0:
			out += "%dd, " % td.days
		hours = td.seconds // 3600
		if hours > 0:
			out += "%dh, " % hours
		minutes = (td.seconds // 60) % 60
		if minutes > 0:
			out += "%dm, " % minutes
		seconds = td.seconds % 60
		if seconds > 0:
			out += "%ds, " % seconds
		return out[:-2]
	
	def _idStr(self, ev):
		"""Returns the event's network-code and event-ID as one string.
		The netcode and ID are simoly cincatenated with a ':' in between.
		"""
		return "%s:%s" % (ev['net'], ev['id'])
	
	def _locStr(self, loc):
		"""Returns a geographic location (a (latitude, longitude) tuple)
		as a string
		"""
		if loc[0] >= 0:
			lat = '%.3f°N' % loc[0]
		else:
			lat = '%.3f°S' % -loc[0]
		if loc[1] >= 0:
			lon = '%.3f°E' % loc[1]
		else:
			lon = '%.3f°W' % -loc[1]
			
		return "%s,%s" % (lat, lon)
	
	def _eventStr(self, ev):
		"""Returns the event's metadata as a string
		"""
		timestring = time.strftime("%b %d %Y - %H:%M:%S UTC", time.localtime(ev['time']))
		out = "%s on %s, mag %.1f" % (self._idStr(ev), timestring, ev['mag'])
		if 'magtype' in ev:
			out += " (%s)" % ev['magtype']
		if 'type' in ev:
			out += ", type '%s'" % ev['type']
		out += ", at %s" % self._locStr(ev['loc'])
		if 'depth' in ev:
			out += ", %.1f km deep" % ev['depth']
		if 'dmin' in ev:
			out += ", %.1f km from nearest station" % ev['dmin']
		if 'qual' in ev:
			out += ", quality %.1f" % ev['qual']
	
		return out
	
	
	def runStp(self, events, stn_count=3, channels='H%'):
		"""Creates and runs an StpWrapper instance.
		First checks the number of running StpWrappers against StpRunner.maxthreads,
		and creates a unique instance-name (STP[n]) for the new StpWrapper
		The provided arguments are passed to the StpWrapper.runStp() method
		This StpRunner's 'verbose', 'outputdir', 'logfd' and 'errfd' members are inherited by the new StpWrapper
		"""
		if type(events) != types.ListType:
			events = [events]
		
		numthreads = len(self.sws)
		if numthreads >= self.maxthreads:
			ev_str = ""
			for ev in events:
				ev_str += "%s, " % self._idStr(ev)
			
			self.errMessage("Warning: Maximum number of STP's (%d) already  running. Waiting with events [%s]" % (self.maxthreads, ev_str[:-2]))
			return
		
		halfthreads = self.maxthreads // 2
		if (numthreads >= halfthreads):
			minevents = 2 + ((numthreads - halfthreads) * 2)
			if len(events) < minevents:
				self.logMessage("%d STP's already  running. Need at least %d events before starting another." % (numthreads, minevents))
				return
		
		with self.sws_lock:
			if numthreads > 0:
				idxs = []
				for sw in self.sws:
					idxs.append(int(sw.name[4:-1]))
				
				for n in range(1, self.maxthreads + 1):
					if n not in idxs:
						break
				
				else:
					ev_str = ""
					for ev in events:
						ev_str += "%s, " % self._idStr(ev)
					
					self.errMessage("Warning: Cannot find free STP index (i <= %d). Waiting with events [%s]" % (self.maxthreads, ev_str[:-2]))
					return
					
				name = "STP[%d]" % n
			else:
				name = "STP[1]"
				
			sw = StpWrapper(name, self.qp, self.stations, self.defaults)
			
			sw.verbose = self.verbose
			sw.logfd = self.logfd
			sw.errfd = self.errfd
			
			sw.outputdir = self.outputdir
			
			for ev in events:
				self.proc[ev['id']] = name
				
			sw.start(events, stn_count, channels)
			self.sws.append(sw)
		
		if (self.verbose & 16) != 0:
			self.logMessage("Processing: %s" % str(self.proc))
		
	def checkEvents(self, events, stn_count=3, channels='H%'):
		"""Check the given events' IDs against the existing events' dir-names in the outputdir.
		then call runStp() with a list of all events that do not have a seismogram-dir yet
		The 'stn_count' and 'channels' arguments are passed to runStp()
		"""
		have = os.listdir(self.outputdir)
		
		if type(events) != types.ListType:
			events = [events]
		
		get_events = []
		for ev in events:
			if (ev['id'] not in have) and (ev['id'] not in self.proc):
				get_events.append(ev)
			
		if len(get_events):
			self.runStp(get_events, stn_count, channels)
		else:
			self.logMessage("No new events in list")
			
	def checkAll(self, stn_count=3, channels='H%'):
		"""Check the IDs of all events currently in the DB against the existing events'
		dir-names in the outputdir. Then call runStp() with a list of all events that
		do not have a seismogram-dir yet
		The 'stn_count' and 'channels' arguments are passed to runStp()
		"""
		have = os.listdir(self.outputdir)
		events = self.qp.getAll()
		
		get_events = []
		old_events = have[:]
		for ev in events:
			if (ev['id'] not in have) and (ev['id'] not in self.proc):
				get_events.append(ev)
			if ev['id'] in have:
				old_events.remove(ev['id'])
			
		if len(get_events):
			self.runStp(get_events, stn_count, channels)
		else:
			self.logMessage("No new events in DB at %s" % time.strftime("%b %d %Y - %H:%M:%S UTC", time.gmtime(self.qp.mtime)))
			
		if len(old_events) and (self.defaults['retainperiod'] >= datetime.timedelta(0)):
			self.cleanDirs(old_events)
	
	def _rmDir(self, ev_dir):
		"""Remove an empty event-dir from the outputdir tree
		"""
		ls = os.listdir(ev_dir)
		for f in ls:
			os.remove(f)
		os.rmdir(ev_dir)
	
	def cleanDirs(self, old_events):
		"""Remove the subdirs of given old_events which are older than the current DB by
		StpRunner.defaults['retainperiod'] from the outputdir tree
		"""
		mtime = datetime.datetime.fromtimestamp(self.qp.mtime)
		for ev_id in old_events:
			ev_dir = os.path.join(self.outputdir, ev_id)
			age = mtime - datetime.datetime.fromtimestamp(os.stat(ev_dir)[stat.ST_MTIME])
			if age > self.defaults['retainperiod']:
				self._rmDir(ev_dir)
				self.logMessage("Removed seismograms-dir for old event %s after %s" % (ev_id, self._tdString(age)))
	
	def garbageCollect(self):
		"""MainLoop of the GarbageCollector-thread.
		Handles the collection and blacklisting of rejected events,
		Removes StpWrappers that are done from the list of currently running StpWrappers
		"""
		self.logMessage("Started at %s" % datetime.datetime.utcnow().strftime("%b %d %Y - %H:%M:%S UTC"))
		while (self.gcrun or self.qp.run or len(self.sws)):
			for sw in reversed(self.sws):
				ev_str = ""
				while len(sw.rejects):
					ev = sw.rejects.pop(0)
					ev_str += "%s, " % self._idStr(ev)
					self.qp.blackListEvent(ev)
				if len(ev_str):
					self.logMessage("%s rejected events [%s]" % (sw.name, ev_str[:-2]))
					
				if sw.isDone():
					with self.sws_lock:
						for (id, name) in self.proc.items():
							if name == sw.name:
								del self.proc[id]
						
						self.sws.remove(sw)
					
					if (self.verbose & 16) != 0:
						self.logMessage("Processing: %s" % str(self.proc))
				elif sw.connected:
					# try to kill any 'stp' subprocess that has remained connected for 15 minutes
					if (sw.connected + datetime.timedelta(0, 0, 0, 0, 15)) < datetime.datetime.utcnow():
						for sig in ("-HUP", "-INT", "-TERM", "-KILL"):
							if subprocess.call(["kill", sig, "%d" % sw.stp.pid]) == 0:
								break
						else:
							self.errMessage("Error: Failed to kill stuck 'stp' process with PID %d" % sw.stp.pid)
							
				
			if (self.verbose & 4) != 0:
				for net in netgroup.keys():
					if self.stn_count[net] != len(self.stations[net]):
						self.stn_count[net] = len(self.stations[net])
						self.logMessage("Net '%s' now has %d stations" % (net, self.stn_count[net]))
			
			time.sleep(1)
			
		self.logMessage("Done at %s" % datetime.datetime.utcnow().strftime("%b %d %Y - %H:%M:%S UTC"))

	def start(self, mainthread_bg=False, num_sta=3, channels='H%', force=False):
		"""Creates and starts the GarbageCollector-thread.
		Starts the QDMParser-thread
		If 'mainthread_bg' == True, starts the runForever() method in its own thread, passing
		the remaining arguments to runForever()
		"""
		if self.gcthread == None:
			self.gcthread = threading.Thread(None, self.garbageCollect, "StpGarbageCollector")
		if not self.gcrun:
			self.gcrun = True
			self.gcthread.start()
		
		if not self.qp.run:
			self.qp.start()
		
		if mainthread_bg and self.mainthread == None:
			self.mainthread = threading.Thread(None, self.runForever, "StpRunner", [num_sta, channels, force])
			self.run = True
			self.mainthread.start()
		
	def stop(self):
		"""Stops all running StpWrappers and waits for thie threads to finish
		Stops the QDMParser and waits for its thread to finish
		If the runForever() method is running, stops it (and waits for its thread to finish, if any)
		Waits 2 seconds, then stops the GarbageCollector and waits for its thread to finish.
		"""
		for sw in reversed(self.sws):
			sw.stop()
		
		if self.qp.run:
			self.qp.stop()
		
		if self.run:
			self.run = False
			if self.mainthread != None:
				self.mainthread.join()
				self.mainthread = None
		
		time.sleep(2)	# allow StpGarbageCollector to run at least once more
		if self.gcrun:
			self.gcrun = False
			if self.gcthread != None:
				self.gcthread.join()
				self.gcthread = None

	def runOnceForMag(self, mags, num_sta=3, channels='H%', force=False):
		"""Look-up the given magnitudes in the DB and call checkEvents() with the resulting
		list of events.
		'mags' can be a float, an int or a list thereof.
		The 'num_sta' and 'channels' arguments are passed to checkEvents()
		If 'force' == True, calls runStp() directly, bypassing checkEvents() and (re-)downloading
		the available seismograms for all resulting events.
		"""
		if (type(mags) == types.ListType) or (type(mags) == types.TupleType):
			events = []
			for mag in mags:
				try:
					events.append(self.qp.getEvent(float(mag)))
				except ValueError:
					raise ValueError("Invalid magnitude-value: %s" % str(mag))
		elif (type(mags) == types.FloatType) or (type(mags) == types.IntType):
			events = [self.qp.getEvent(float(mags))]
		else:
			raise ValueError("Invalid magnitude-value: %s" % str(mags))
			
		if force:
			self.runStp(events, num_sta, channels)
		else:
			self.checkEvents(events, num_sta, channels)
		
	def runOnceForAll(self, num_sta=3, channels='H%', force=False):
		"""call checkAll(), passing it the 'num_sta' and 'channels' arguments
		If 'force' == True, calls runStp() directly with all events currently in the DB,
		bypassing checkAll() and (re-)downloading the available seismograms for all events.
		"""
		if force:
			self.runStp(self.qp.getAll(), num_sta, channels)
		else:
			self.checkAll(num_sta, channels)
		
	def runForever(self, num_sta=3, channels='H%', force=False):
		"""MainLoop for the 'auto' mode
		Wait for the DB to be updated, then call runOnceForAll(), passing it the provided arguments.
		Repeat.
		"""
		while self.run:
			self.qp.wait(1)
			
			if self.qp.isReady():
				self.runOnceForAll(num_sta, channels, force)
		
		if self.gcrun or self.qp.run:
			self.stop()
			
	def reload(self):
		"""Reload the blacklist-file, re-parse the DB-file
		(see QDMParser.reload())
		"""
		self.qp.reload()
		if (self.verbose & 32) != 0:
			self.logMessage("Blacklisted IDs: %s" % str(self.qp.blacklist.keys()))
		if (self.verbose & 64) != 0:
			self.logMessage("DB IDs: %s" % str(self.qp.getAllIds()))


if __name__ == '__main__':
	import readline, signal
	
	from optparse import OptionParser
	
	op = OptionParser()
	# Define command-line options
	op.add_option("-v", "--verbose", action='store', type='string', dest='verbose', metavar='V',
					help="set verbosity (a bitmask) [default = 0]")
	op.add_option("-d", "--outputdir", action='store', type='string', dest='outputdir', metavar='DIR',
					help="save seismograms in DIR. (DIR will be created if it doesn't exist) [default = /var/lib/STP]")
	op.add_option("-m", "--mag", action='append', type='float', dest='mag', 
					help="run once for magnitude MAG")
	op.add_option("-a", "--all", action='store_true', dest='all', 
					help="get seismograms for all events")
	op.add_option("-u", "--auto", action='store_true', dest='auto', 
					help="automatically keep getting seismograms for new events (implies '-a')")
	op.add_option("-t", "--threads", action='store', type='int', dest='num_thr', metavar='N',
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
	
	# Set default values
	op.set_defaults(num_sta=3)
	op.set_defaults(num_thr=10)
	op.set_defaults(channels='H%')
	op.set_defaults(retper='1d')
	op.set_defaults(keepper='30d')
	op.set_defaults(outputdir='/var/lib/STP')
	
	# Parse command-line options
	(opts, args) = op.parse_args()
	
	# Create StpRunner
	sr = StpRunner(outputdir=opts.outputdir)
	
	if opts.verbose != None:
		# Parse verbosity argument
		verbose = 0
		try:					# try binary first...
			verbose = int(opts.verbose, 2)
		except ValueError:
			try:				# ... then decimal ...
				verbose = int(opts.verbose)
			except ValueError:	# ... then hexadecimal
				x = opts.verbose.find('x')
				hex = opts.verbose[(x + 1):]
				try:
					verbose = int(hex, 16)
				except ValueError:
					sys.stderr.write("Invalid verbosity argument '%s'" % opts.verbose)
	
		sr.setVerbose(verbose)
	
	# check provided max-number-of-threads argument
	if opts.num_thr > 1:
		sr.maxthreads = opts.num_thr
	else:
		raise ValueError("Invalid number-of-threads argument: %s" % str(opts.num_thr))
	
	# set retry- and retain-periods
	sr.setRetryPeriod(opts.retper)
	sr.setRetainPeriod(opts.keepper)
	
	# define a user-input function to let the user enter a (list of) magnitude(s)
	def getUserMag():
		while sr.qp.run:
			inp = raw_input("Enter Magnitude values [? for help]\n> ")
			if not len(inp):
				continue
			
			try:
				magnitudes = []
				for values in inp.split():
					for val in values.split(','):
						magnitudes.append(float(val))
						
				return magnitudes
			
			except ValueError:
				if val.lower().startswith('l'):
					timestring = time.strftime("%b %d %Y - %H:%M:%S UTC", time.gmtime(sr.qp.mtime))
					print "on \t %s: %d Events" % (timestring, len(sr.qp.db))
					print "Mag \t Date          Time \t\tNet:ID \t\t Lati      Long \t Depth \t\t Dmin"
					print sr.qp
					print
				elif val.lower().startswith('a'):
					print "Getting ALL"
					print
					return 'ALL'
				elif val.lower().startswith('q'):
					print "Quit"
					print
					sr.stop()
					exit(0)
				else:
					print "Usage:"
					print "Enter a (list of) magnitude-value(s) as integer or floating-point number(s)"
					print "      list-items should be separated by spaces or commas"
					print "Enter 'ls' (or 'l') for a list of currently available events"
					print "Enter 'all' (or 'a') to download seismograms for all available events"
					print "Enter 'quit' (or 'q') to exit the program"
					print
			
	# Define a signal-handler to stop the StpRunner and its sub-processes & threads
	def stophandler(sig, frame):
		print "\nGot signal %d" % sig
		sr.stop()
	
	# Define a signal-handler for realoding the blaclist and event-DB
	def reloadhandler(sig, frame):
		print "\nGot signal %d" % sig
		sr.reload()
	
	# Register signal-handlers
	signal.signal(signal.SIGINT, stophandler)
	signal.signal(signal.SIGQUIT, stophandler)
	signal.signal(signal.SIGHUP, reloadhandler)

	# One-shot mode
	if ((opts.mag != None) or (opts.all != None)) and (opts.auto == None):
		sr.qp.parse()
		
		if opts.all:
			sr.runOnceForAll(opts.num_sta, opts.channels, opts.force)
		else:
			sr.runOnceForMag(opts.mag, opts.num_sta, opts.channels, opts.force)
		
		# run StpGarbageCollector to handle StpWrapper-thread exits (and KeyboardInterrupts) correctly
		sr.garbageCollect()
		
		exit(0)
	
	# Auto mode
	if opts.auto:
		try:
			# start StpGarbageCollector and QDMParser in their own threads
			sr.start(True, opts.num_sta, opts.channels, opts.force)
			
			# then simply wait for the mainthread to exit
			while (sr.mainthread != None) and sr.mainthread.isAlive():
				time.sleep(1)
			
		finally:
			print "Quitting"
			
			if sr.gcrun or sr.qp.run:
				sr.stop()
			
		exit(0)
		
	# Main loop for interactive mode
	try:
		# start StpGarbageCollector and QDMParser in their own threads
		# does NOT start the StpRunner's mainloop
		sr.start()
		
		while sr.qp.run:
			if not sr.qp.isReady():
				sr.qp.wait()
				
			# ask user to enter (a) magnitude(s) 
			mag = getUserMag()
			if mag == None:
				continue
			
			if mag == 'ALL':
				sr.runOnceForAll(opts.num_sta, opts.channels, opts.force)
			else:
				sr.runOnceForMag(mag, opts.num_sta, opts.channels, opts.force)
			
	finally:
		print "Quitting"
		
		if sr.gcrun or sr.qp.run:
			sr.stop()
		
	exit(0)	
		
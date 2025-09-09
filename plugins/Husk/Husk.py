#!/usr/bin/env python3

from Deadline.Plugins import DeadlinePlugin, PluginType
from Deadline.Scripting import FileUtils, SystemUtils, RepositoryUtils, FrameUtils, StringUtils
import os

def GetDeadlinePlugin():
	"""This is the function that Deadline calls to get an instance of the
	main DeadlinePlugin class.
	"""
	return HuskPlugin()

def CleanupDeadlinePlugin(deadlinePlugin):
	"""This is the function that Deadline calls when the plugin is no
	longer in use so that it can get cleaned up.
	"""
	deadlinePlugin.Cleanup()


class HuskPlugin(DeadlinePlugin):
	"""This is the main DeadlinePlugin class for Husk."""
	def __init__(self):
		super().__init__()  # Call the parent class constructor
		"""Hook up the callbacks in the constructor."""
		self.InitializeProcessCallback += self.InitializeProcess
		self.RenderExecutableCallback += self.RenderExecutable
		self.RenderArgumentCallback += self.RenderArgument	
		
		
	def _set_env_vars(self):
		# EITHER: read global Plugin Configuration value from .param
		block = self.GetConfigEntryWithDefault("ExtraEnv", "")
		# OR: read per-job value from .options / PluginInfo
		# block = self.GetPluginInfoEntryWithDefault("ExtraEnv", "")

		if not block:
			return

		env_map = _parse_env_block(block, self.LogWarning)
		for k, v in env_map.items():
			# Map any repo path tokens or OS path translations
			v = RepositoryUtils.CheckPathMapping(v)  # maps \\server/win to /mnt/server on Linux, etc.
			v = os.path.expandvars(v)                # expand %FOO% / $FOO if present
			self.SetProcessEnvironmentVariable(k, v) # applies to processes launched by this plugin
			self.LogInfo("ENV set for render process: {}={}".format(k, v))

	def Cleanup(self):
		for stdoutHandler in self.StdoutHandlers:
			del stdoutHandler.HandleCallback
		
		del self.InitializeProcessCallback
		del self.RenderExecutableCallback
		del self.RenderArgumentCallback

	

	def InitializeProcess(self):
		"""Called by Deadline to initialize the plugin."""
		# Set env exactly once when the managed process is being initialized
		self._set_env_vars()
		
		# Set the plugin specific settings.
		self.SingleFramesOnly = False  # Allow multi-frame chunks
		self.StdoutHandling = True
		self.PluginType = PluginType.Simple
		
		# Progress updates
		self.AddStdoutHandlerCallback('ALF_PROGRESS ([0-9]+)').HandleCallback += self.HandleStdoutProgress
		# Detect Errors
		self.AddStdoutHandlerCallback('Error:(.*)').HandleCallback += self.HandleStdoutError
		self.AddStdoutHandlerCallback('USD ERROR(.*)').HandleCallback += self.HandleStdoutError 

	def RenderExecutable(self):
		huskExecList = self.GetConfigEntry('HuskRenderExecutable')
		huskExec = FileUtils.SearchFileList(huskExecList)

		if huskExec == '':
			self.FailRender(
				'Husk render executable could not be found in the semicolon-separated list \"%s\". '
				'The path to the render executable can be configured from the Plugin Configuration in the Deadline Monitor.'
				% (huskExec)
			)

		return huskExec

	def RenderArgument(self):
		arguments = ''
		
		# Get scene file to be rendered and check path 
		usdFile = self.GetPluginInfoEntry('SceneFile')
		usdFile = RepositoryUtils.CheckPathMapping(usdFile)
		usdFile = usdFile.replace('\\', '/')
		
		outFile = self.GetPluginInfoEntry('ImageOutputDirectory')
		outFile = RepositoryUtils.CheckPathMapping(outFile)
		outFile = outFile.replace('\\', '/')
		
		width = self.GetPluginInfoEntry('Width')
		height = self.GetPluginInfoEntry('Height')
		overrideres = self.GetPluginInfoEntry('OverrideResolution')
		overriderender = self.GetPluginInfoEntry('OverrideRenderDelegate')
		renderdelegate = self.GetPluginInfoEntry('RenderDelegate')
		try:
			renderpass = self.GetPluginInfoEntry('RenderPass')
		except:
			renderpass = ""
		customargs = self.GetPluginInfoEntry('CustomArguments')
		logLevel = self.GetPluginInfoEntry('LogLevel')

		# Get the frame range for the chunk
		startFrame = self.GetStartFrame()
		endFrame = self.GetEndFrame()
		chunk = self.GetJobInfoEntry('ChunkSize')
		chunk = min(endFrame - startFrame + 1, int(chunk))

		# Construct Husk command with multiple frames
		arguments += usdFile + ' '
		arguments += '--verbose a{} '.format(logLevel)
		arguments += '--frame {} '.format(startFrame)
		arguments += '--frame-count {} '.format(chunk)          
		
		# -- frame-list only takes space separated list of frames, so using above frame count instead to handle chunk sizes
		#frameList = self.GetPluginInfoEntry('FrameList')
		#frameList = frameList.replace('-', ' ')  # Replace hyphen with a space
		#arguments += '--frame-list {} '.format(frameList)

		if overrideres:
			arguments += '--res {0} {1} '.format(width, height)
		if renderpass:
			arguments += '--pass {0} '.format(renderpass)
		if overriderender:
			arguments += '-R {0} '.format(renderdelegate)
		arguments += customargs + ' '
		arguments += '-o ' + outFile
		arguments += ' --make-output-path' + ' '
		
		self.LogInfo('Rendering USD file: ' + usdFile)
		self.LogInfo('Rendering frames: {}-{}'.format(startFrame, endFrame))

		return arguments

	def HandleStdoutProgress(self):
		self.SetStatusMessage(self.GetRegexMatch(0))
		self.SetProgress(float(self.GetRegexMatch(1)))

	def HandleStdoutError(self):
		self.FailRender(self.GetRegexMatch(0))


def _parse_env_block(text, log):
	env = {}
	for raw in text.splitlines():
		line = raw.strip()
		if not line or line.startswith('#') or line.startswith(';'):
			continue
		# allow KEY=VALUE;KEY2=VALUE2 on one line too
		parts = [p for p in line.split(';') if p.strip()] if ';' in line else [line]
		for p in parts:
			if '=' not in p:
				log("Skipping invalid env spec: {}".format(p))
				continue
			k, v = p.split('=', 1)
			env[k.strip()] = v.strip()
	return env


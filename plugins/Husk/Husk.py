#!/usr/bin/env python3

from Deadline.Plugins import DeadlinePlugin, PluginType
from Deadline.Scripting import FileUtils, SystemUtils, RepositoryUtils, FrameUtils, StringUtils
import os
import platform

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
		self.RenderTasksCallback += self.RenderTasks
		
		
	# ---------- ENV HELPERS ----------

	
	def _detect_os(self):
		"""Return one of: 'Windows', 'Linux', 'OSX'."""
		try:
			if hasattr(SystemUtils, "IsRunningOnWindows") and SystemUtils.IsRunningOnWindows():
				return "Windows"
			if hasattr(SystemUtils, "IsRunningOnLinux") and SystemUtils.IsRunningOnLinux():
				return "Linux"
			# Some Deadline versions expose IsRunningOnOSX, others IsRunningOnMac
			if hasattr(SystemUtils, "IsRunningOnOSX") and SystemUtils.IsRunningOnOSX():
				return "OSX"
			if hasattr(SystemUtils, "IsRunningOnMac") and SystemUtils.IsRunningOnMac():
				return "OSX"
		except Exception:
			pass

		# Fallback to stdlib
		sysname = platform.system()
		if sysname == "Windows":
			return "Windows"
		if sysname == "Darwin":
			return "OSX"
		return "Linux"

	def _get_env_text_for_worker(self):
		"""Pick the right env blocks for this Worker OS, then concatenate."""
		os_suffix = self._detect_os()

		# Per-job first (from .options)
		job_os  = self.GetPluginInfoEntryWithDefault(f"ExtraEnv{os_suffix}", "")
		job_any = self.GetPluginInfoEntryWithDefault("ExtraEnv", "")

		# Global fallback (from .param)
		cfg_os  = self.GetConfigEntryWithDefault(f"ExtraEnv{os_suffix}", "")
		cfg_any = self.GetConfigEntryWithDefault("ExtraEnv", "")

		parts = [job_os, job_any, cfg_os, cfg_any]
		return "\n".join(t for t in parts if t and t.strip())

	def _parse_env_block(self, text):
		env = {}
		if not text:
			return env
		for raw in text.splitlines():
			line = raw.strip()
			if not line or line.startswith('#') or line.startswith(';'):
				continue
			chunks = [p for p in line.split(';') if p.strip()] if ';' in line else [line]
			for p in chunks:
				if '=' not in p:
					self.LogWarning("Skipping invalid env spec: {}".format(p))
					continue
				k, v = p.split('=', 1)
				k, v = k.strip(), v.strip()
				# strip surrounding quotes
				if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
					v = v[1:-1]
				env[k] = v
		return env

	def _set_env_vars(self):
		block = self._get_env_text_for_worker()
		if not block:
			self.LogInfo("No ExtraEnv entries found for this OS.")
			return

		env_map = self._parse_env_block(block)
		for k, v in env_map.items():
			v = RepositoryUtils.CheckPathMapping(v)
			v = os.path.expandvars(v)

			# Optional: append semantics for PATH-like vars
			if k.upper() in ("PATH", "PYTHONPATH", "HOUDINI_PATH"):
				existing = os.environ.get(k)
				if existing:
					v = existing + os.pathsep + v

			self.SetProcessEnvironmentVariable(k, v)
			os.environ[k] = v

			redacted = ("*" * 8) if any(s in k.upper() for s in ("PASS", "TOKEN", "SECRET", "KEY")) else v
			self.LogInfo("ENV set for render process: {}={}".format(k, redacted))

	def Cleanup(self):
		for stdoutHandler in self.StdoutHandlers:
			del stdoutHandler.HandleCallback

		del self.InitializeProcessCallback
		del self.RenderExecutableCallback
		del self.RenderArgumentCallback
		del self.RenderTasksCallback

	

	def InitializeProcess(self):
		"""Called by Deadline to initialize the plugin."""
		# The cleanup job deletes tile files directly in Python, so it runs as an
		# Advanced plugin (no managed external process) and skips env/stdout setup.
		if self._get_bool('CleanupJob'):
			self.PluginType = PluginType.Advanced
			return

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

	def _get_bool(self, key, default=False):
		"""Read a plugin-info entry as a boolean, tolerating missing keys."""
		val = self.GetPluginInfoEntryWithDefault(key, str(default))
		return str(val).strip().lower() in ('1', 'true', 'yes', 'on')

	def _husk_dir(self):
		"""Return the directory containing the configured husk executable."""
		huskExecList = self.GetConfigEntry('HuskRenderExecutable')
		huskExec = FileUtils.SearchFileList(huskExecList)
		if huskExec == '':
			self.FailRender(
				'Husk render executable could not be found in the semicolon-separated list \"%s\". '
				'The path to the render executable can be configured from the Plugin Configuration in the Deadline Monitor.'
				% (huskExecList)
			)
		return huskExec, os.path.dirname(huskExec)

	def RenderExecutable(self):
		# Assembly tasks use itilestitch, which ships alongside husk in the Houdini
		# bin directory. Resolving it relative to the configured husk path means the
		# correct per-OS executable is used on a mixed farm without extra config.
		if self._get_bool('AssemblyJob'):
			_, huskDir = self._husk_dir()
			stitchName = 'itilestitch.exe' if self._detect_os() == 'Windows' else 'itilestitch'
			stitchExec = os.path.join(huskDir, stitchName)
			if not os.path.isfile(stitchExec):
				self.FailRender('itilestitch executable could not be found at "%s".' % stitchExec)
			return stitchExec

		huskExec, _ = self._husk_dir()
		return huskExec

	def _tile_filename(self, outFile, tileIndex):
		"""Insert husk's --tile-suffix token before the extension for a given tile.

		Husk expands the printf-style suffix (e.g. _tile%02d) with the tile index,
		so we replicate that here to know each tile's output path for assembly.
		"""
		suffix = self.GetPluginInfoEntryWithDefault('TileSuffix', '_tile%d')
		root, ext = os.path.splitext(outFile)
		try:
			expanded = suffix % tileIndex
		except (TypeError, ValueError):
			expanded = '_tile{}'.format(tileIndex)
		return root + expanded + ext

	def RenderTasks(self):
		"""Advanced-plugin entry point. Only the cleanup job uses this path:
		it deletes the per-tile image files after assembly has completed.
		Simple-plugin (render/assembly) jobs never reach here.
		"""
		if not self._get_bool('CleanupJob'):
			return

		outFile = self.GetPluginInfoEntry('ImageOutputDirectory')
		outFile = RepositoryUtils.CheckPathMapping(outFile)
		outFile = outFile.replace('\\', '/').strip('"')

		tilesX = int(self.GetPluginInfoEntryWithDefault('TilesX', '1'))
		tilesY = int(self.GetPluginInfoEntryWithDefault('TilesY', '1'))
		totalTiles = tilesX * tilesY

		removed = 0
		for i in range(totalTiles):
			tileFile = self._tile_filename(outFile, i)
			try:
				if os.path.isfile(tileFile):
					os.remove(tileFile)
					removed += 1
					self.LogInfo('Removed tile: {}'.format(tileFile))
				else:
					self.LogInfo('Tile not found (skipping): {}'.format(tileFile))
			except OSError as e:
				# Don't fail the job over a single un-deletable tile.
				self.LogWarning('Could not remove tile {}: {}'.format(tileFile, e))

		self.LogInfo('Tile cleanup complete: removed {} of {} tiles.'.format(removed, totalTiles))

	def AssemblyArgument(self):
		"""Build the itilestitch command line: <output> <tile0> <tile1> ..."""
		outFile = self.GetPluginInfoEntry('ImageOutputDirectory')
		outFile = RepositoryUtils.CheckPathMapping(outFile)
		outFile = outFile.replace('\\', '/').strip('"')

		tilesX = int(self.GetPluginInfoEntryWithDefault('TilesX', '1'))
		tilesY = int(self.GetPluginInfoEntryWithDefault('TilesY', '1'))
		totalTiles = tilesX * tilesY

		tileFiles = [self._tile_filename(outFile, i) for i in range(totalTiles)]

		self.LogInfo('Assembling {} tiles into: {}'.format(totalTiles, outFile))

		arguments = '"{}"'.format(outFile)
		for tf in tileFiles:
			arguments += ' "{}"'.format(tf)
		return arguments

	def RenderArgument(self):
		if self._get_bool('AssemblyJob'):
			return self.AssemblyArgument()

		arguments = ''

		# Get scene file to be rendered and check path
		usdFile = self.GetPluginInfoEntry('SceneFile')
		usdFile = RepositoryUtils.CheckPathMapping(usdFile)
		usdFile = usdFile.replace('\\', '/').strip('"')

		outFile = self.GetPluginInfoEntry('ImageOutputDirectory')
		outFile = RepositoryUtils.CheckPathMapping(outFile)
		outFile = outFile.replace('\\', '/').strip('"')

		width = self.GetPluginInfoEntry('Width')
		height = self.GetPluginInfoEntry('Height')
		overrideres = self._get_bool('OverrideResolution')
		overriderender = self._get_bool('OverrideRenderDelegate')
		renderdelegate = self.GetPluginInfoEntry('RenderDelegate')
		try:
			renderpass = self.GetPluginInfoEntry('RenderPass')
		except:
			renderpass = ""
		customargs = self.GetPluginInfoEntry('CustomArguments')
		customargs = RepositoryUtils.CheckPathMapping(customargs)  # apply path mapping

		logLevel = self.GetPluginInfoEntry('LogLevel')

		tileRendering = self._get_bool('TileRendering')

		if tileRendering:
			# Each Deadline task is one tile; the task number is the tile index.
			# The actual frame to render is stored separately because the task
			# range is repurposed to enumerate tiles (single-frame tiling).
			tileIndex = self.GetStartFrame()
			renderFrame = self.GetPluginInfoEntryWithDefault('RenderFrame', str(tileIndex))
			tilesX = int(self.GetPluginInfoEntryWithDefault('TilesX', '1'))
			tilesY = int(self.GetPluginInfoEntryWithDefault('TilesY', '1'))
			tileSuffix = self.GetPluginInfoEntryWithDefault('TileSuffix', '_tile%d')

			arguments += '"{}" '.format(usdFile)
			arguments += '--verbose a{} '.format(logLevel)
			arguments += '--frame {} '.format(renderFrame)
			arguments += '--frame-count 1 '
			arguments += '--tile-count {} {} '.format(tilesX, tilesY)
			arguments += '--tile-index {} '.format(tileIndex)
			arguments += '--tile-suffix {} '.format(tileSuffix)
		else:
			# Get the frame range for the chunk
			startFrame = self.GetStartFrame()
			endFrame = self.GetEndFrame()
			chunk = self.GetJobInfoEntry('ChunkSize')
			chunk = min(endFrame - startFrame + 1, int(chunk))

			# Construct Husk command with multiple frames
			arguments += '"{}" '.format(usdFile)
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
		arguments += '-o "{}"'.format(outFile)
		arguments += ' --make-output-path' + ' '

		self.LogInfo('Rendering USD file: ' + usdFile)
		if tileRendering:
			self.LogInfo('Rendering tile {} of {}x{}'.format(self.GetStartFrame(), self.GetPluginInfoEntryWithDefault('TilesX', '1'), self.GetPluginInfoEntryWithDefault('TilesY', '1')))
		else:
			self.LogInfo('Rendering frames: {}-{}'.format(self.GetStartFrame(), self.GetEndFrame()))

		return arguments

	def HandleStdoutProgress(self):
		self.SetStatusMessage(self.GetRegexMatch(0))
		# husk's ALF_PROGRESS can exceed 100% (it accumulates across tiles/buckets
		# rather than normalizing to the final image), so clamp to a sane 0-100.
		try:
			progress = float(self.GetRegexMatch(1))
		except ValueError:
			return
		progress = max(0.0, min(100.0, progress))
		self.SetProgress(progress)

	def HandleStdoutError(self):
		self.FailRender(self.GetRegexMatch(0))



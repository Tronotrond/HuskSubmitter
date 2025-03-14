#!/usr/bin/env python3

from Deadline.Plugins import DeadlinePlugin, PluginType
from Deadline.Scripting import FileUtils, SystemUtils, RepositoryUtils, FrameUtils, StringUtils

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

    def Cleanup( self ):
        for stdoutHandler in self.StdoutHandlers:
            del stdoutHandler.HandleCallback
        
        del self.InitializeProcessCallback
        del self.RenderExecutableCallback
        del self.RenderArgumentCallback

    def InitializeProcess(self):
        """Called by Deadline to initialize the plugin."""
        # Set the plugin specific settings.
        self.SingleFramesOnly=True
        self.StdoutHandling=True
        #self.PopupHandling=True
        self.PluginType = PluginType.Simple
        
        # Progress updates
        self.AddStdoutHandlerCallback('ALF_PROGRESS ([0-9]+)').HandleCallback += self.HandleStdoutProgress
        # Detect Errors
        self.AddStdoutHandlerCallback('Error:(.*)').HandleCallback += self.HandleStdoutError
        self.AddStdoutHandlerCallback('USD ERROR(.*)').HandleCallback += self.HandleStdoutError 
        
        
    def RenderExecutable( self ):
        huskExecList = self.GetConfigEntry('HuskRenderExecutable')
         
        huskExec = FileUtils.SearchFileList(huskExecList)
        if(huskExec == ''):
            self.FailRender('Husk render executable could not be found in the semicolon separated list \"%s\". The path to the render executable can be configured from the Plugin Configuration in the Deadline Monitor.' % (huskExec) )
        
        return huskExec
        
    def RenderArgument( self ):
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
        customargs = self.GetPluginInfoEntry('CustomArguments')
        logLevel = self.GetPluginInfoEntry('LogLevel')

        # Added better handling of Deadline ChunkSize > 1, avoiding reloading the plugin and assets for each frame
        startFrame = self.GetStartFrame()
        endFrame = self.GetEndFrame()
        chunk = self.GetJobInfoEntry('ChunkSize')
        
        arguments += usdFile + ' ' 
        arguments += '--verbose a{} '.format(logLevel)
        arguments += '--frame {} '.format(startFrame)
        arguments += '--frame-count {} '.format(chunk)
        
        if overrideres:
            arguments += '--res {0} {1} '.format(width, height)
        if overriderender:
            arguments += '-R {0} '.format(renderdelegate)
        arguments += customargs + ' '
        arguments += '-o ' + outFile
        arguments += ' --make-output-path' + ' '
        
        self.LogInfo('Rendering USD file: ' + usdFile)
        
        return arguments
        
        
    def HandleStdoutProgress(self):
        self.SetStatusMessage(self.GetRegexMatch(0))
        self.SetProgress(float(self.GetRegexMatch(1)))
        #self.SuppressThisLine()
        
    def HandleStdoutError(self):
        self.FailRender(self.GetRegexMatch(0))

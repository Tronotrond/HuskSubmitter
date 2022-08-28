########################################################################
# HUSK USD Scene submission script
# Tronotools - Trond Hille 2022
#
# Submit and render .USD scenes with the standalone Husk renderer
#
# Requirements:
#   - usd-core installed on repository
#
########################################################################
from __future__ import absolute_import
import os
from typing import Any, Tuple

from pxr import Usd, Vt
import re

#from System import *
from System.Collections.Specialized import StringCollection
from System.IO import Path, StreamWriter, File, Directory
from System.Text import Encoding

from Deadline.Scripting import RepositoryUtils, FrameUtils, ClientUtils, PathUtils
from DeadlineUI.Controls.Scripting.DeadlineScriptDialog import DeadlineScriptDialog

from ThinkboxUI.Controls.Scripting.CheckBoxControl import CheckBoxControl
from ThinkboxUI.Controls.Scripting.RangeControl import RangeControl
from ThinkboxUI.Controls.Scripting.TextControl import TextControl
from ThinkboxUI.Controls.Scripting.ButtonControl import ButtonControl


########################################################################
## Globals
########################################################################
scriptDialog = None  # type: DeadlineScriptDialog
settings = None

########################################################################
## Main HUSK function called by Deadline
########################################################################

def __main__(*args):
    global scriptDialog
    global settings
    
    scriptDialog = DeadlineScriptDialog()
    scriptDialog.SetTitle( "Submit Husk USD Job To Deadline" )
    scriptDialog.SetIcon( scriptDialog.GetIcon( 'Husk' ) )
    
    scriptDialog.AddTabControl( "Tabs", 0, 0 )
    
    scriptDialog.AddTabPage( "Job Options" )
    scriptDialog.AddGrid()
    scriptDialog.AddControlToGrid( "Separator1", "SeparatorControl", "Job Description", 0, 0, colSpan=2 )

    scriptDialog.AddControlToGrid( "NameLabel", "LabelControl", "Job Name", 1, 0, "The name of your job. This is optional, and if left blank, it will default to 'Untitled'.", False )
    scriptDialog.AddControlToGrid( "NameBox", "TextControl", "Untitled", 1, 1 )

    scriptDialog.AddControlToGrid( "CommentLabel", "LabelControl", "Comment", 2, 0, "A simple description of your job. This is optional and can be left blank.", False )
    scriptDialog.AddControlToGrid( "CommentBox", "TextControl", "", 2, 1)

    scriptDialog.AddControlToGrid( "DepartmentLabel", "LabelControl", "Department", 3, 0, "The department you belong to. This is optional and can be left blank.", False )
    scriptDialog.AddControlToGrid( "DepartmentBox", "TextControl", "", 3, 1 )
    scriptDialog.EndGrid()

    scriptDialog.AddGrid()
    scriptDialog.AddControlToGrid( "Separator2", "SeparatorControl", "Job Options", 0, 0, colSpan=3 )
    
    scriptDialog.AddControlToGrid( "PoolLabel", "LabelControl", "Pool", 1, 0, "The pool that your job will be submitted to.", False )
    scriptDialog.AddControlToGrid( "PoolBox", "PoolComboControl", "none", 1, 1 )

    scriptDialog.AddControlToGrid( "SecondaryPoolLabel", "LabelControl", "Secondary Pool", 2, 0, "The secondary pool lets you specify a Pool to use if the primary Pool does not have any available Workers.", False )
    scriptDialog.AddControlToGrid( "SecondaryPoolBox", "SecondaryPoolComboControl", "", 2, 1 )

    scriptDialog.AddControlToGrid( "GroupLabel", "LabelControl", "Group", 3, 0, "The group that your job will be submitted to.", False )
    scriptDialog.AddControlToGrid( "GroupBox", "GroupComboControl", "none", 3, 1 )

    scriptDialog.AddControlToGrid( "PriorityLabel", "LabelControl", "Priority", 4, 0, "A job can have a numeric priority ranging from 0 to 100, where 0 is the lowest priority and 100 is the highest priority.", False )
    scriptDialog.AddRangeControlToGrid( "PriorityBox", "RangeControl", RepositoryUtils.GetMaximumPriority() // 2, 0, RepositoryUtils.GetMaximumPriority(), 0, 1, 4, 1 )

    scriptDialog.AddControlToGrid( "TaskTimeoutLabel", "LabelControl", "Task Timeout", 5, 0, "The number of minutes a Worker has to render a task for this job before it requeues it. Specify 0 for no limit.", False )
    scriptDialog.AddRangeControlToGrid( "TaskTimeoutBox", "RangeControl", 0, 0, 1000000, 0, 1, 5, 1 )
    scriptDialog.AddSelectionControlToGrid( "AutoTimeoutBox", "CheckBoxControl", False, "Enable Auto Task Timeout", 5, 2, "If the Auto Task Timeout is properly configured in the Repository Options, then enabling this will allow a task timeout to be automatically calculated based on the render times of previous frames for the job. " )

    scriptDialog.AddControlToGrid( "ConcurrentTasksLabel", "LabelControl", "Concurrent Tasks", 6, 0, "The number of tasks that can render concurrently on a single Worker. This is useful if the rendering application only uses one thread to render and your Workers have multiple CPUs.", False )
    scriptDialog.AddRangeControlToGrid( "ConcurrentTasksBox", "RangeControl", 1, 1, 16, 0, 1, 6, 1 )
    scriptDialog.AddSelectionControlToGrid( "LimitConcurrentTasksBox", "CheckBoxControl", True, "Limit Tasks To Worker's Task Limit", 6, 2, "If you limit the tasks to a Worker's task limit, then by default, the Worker won't dequeue more tasks then it has CPUs. This task limit can be overridden for individual Workers by an administrator." )

    scriptDialog.AddControlToGrid( "MachineLimitLabel", "LabelControl", "Machine Limit", 7, 0, "Use the Machine Limit to specify the maximum number of machines that can render your job at one time. Specify 0 for no limit.", False )
    scriptDialog.AddRangeControlToGrid( "MachineLimitBox", "RangeControl", 0, 0, 1000000, 0, 1, 7, 1 )
    scriptDialog.AddSelectionControlToGrid( "IsBlacklistBox", "CheckBoxControl", False, "Machine List Is A Deny List", 7, 2, "You can force the job to render on specific machines by using an allow list, or you can avoid specific machines by using a deny list." )

    scriptDialog.AddControlToGrid( "MachineListLabel", "LabelControl", "Machine List", 8, 0, "The list of machines on the deny list or allow list.", False )
    scriptDialog.AddControlToGrid( "MachineListBox", "MachineListControl", "", 8, 1, colSpan=2 )

    scriptDialog.AddControlToGrid( "LimitGroupLabel", "LabelControl", "Limits", 9, 0, "The Limits that your job requires.", False )
    scriptDialog.AddControlToGrid( "LimitGroupBox", "LimitGroupControl", "", 9, 1, colSpan=2 )

    scriptDialog.AddControlToGrid( "DependencyLabel", "LabelControl", "Dependencies", 10, 0, "Specify existing jobs that this job will be dependent on. This job will not start until the specified dependencies finish rendering.", False )
    scriptDialog.AddControlToGrid( "DependencyBox", "DependencyControl", "", 10, 1 )

    scriptDialog.AddControlToGrid( "OnJobCompleteLabel", "LabelControl", "On Job Complete", 11, 0, "If desired, you can automatically archive or delete the job when it completes.", False )
    scriptDialog.AddControlToGrid( "OnJobCompleteBox", "OnJobCompleteControl", "Nothing", 11, 1 )
    scriptDialog.AddSelectionControlToGrid( "SubmitSuspendedBox", "CheckBoxControl", False, "Submit Job As Suspended", 11, 2, "If enabled, the job will submit in the suspended state. This is useful if you don't want the job to start rendering right away. Just resume it from the Monitor when you want it to render.", False )
    scriptDialog.EndGrid()
    scriptDialog.EndTabPage()
    
    scriptDialog.AddTabPage( "Husk Options" )
    scriptDialog.AddGrid()

    scriptDialog.AddControlToGrid( "Separator3", "SeparatorControl", "Husk Options", 0, 0, colSpan=4 )

    scriptDialog.AddControlToGrid( "SceneLabel", "LabelControl", "USD File", 1, 0, "The USD file(s) to be rendered.", False )
    sceneBox = scriptDialog.AddSelectionControlToGrid( "SceneBox", "FileBrowserControl", "", "USD Files (*.usd);;All Files (*)", 1, 1, colSpan=3 )
    sceneBox.ValueModified.connect( FileLoaded )

    scriptDialog.AddControlToGrid( "FramesLabel", "LabelControl", "Frame List", 2, 0, "The frame range to render.", False )
    scriptDialog.AddControlToGrid( "FramesBox", "TextControl", "", 2, 1 )

    scriptDialog.AddControlToGrid( "WidthLabel", "LabelControl", "Width", 12, 0, "Width of the image." )
    scriptDialog.AddRangeControlToGrid( "WidthBox", "RangeControl", 800, 1, 50000, 0, 1, 12, 1, "Width" )

    scriptDialog.AddControlToGrid( "HeightLabel", "LabelControl", "Height", 12, 2, "Height of the image." )
    scriptDialog.AddRangeControlToGrid( "HeightBox", "RangeControl", 600, 1, 50000, 0, 1, 12, 3, "Height" )


    scriptDialog.AddControlToGrid( "ImageOutputLabel", "LabelControl", "Image Output Directory", 4, 0, "Custom rendering output path.", False )
    scriptDialog.AddSelectionControlToGrid( "ImageOutputBox", "FolderBrowserControl", "", "", 4, 1, colSpan=3 )

    scriptDialog.EndGrid()
    scriptDialog.EndTabPage()
    
    scriptDialog.EndTabControl()
    
    scriptDialog.AddGrid()
    scriptDialog.AddHorizontalSpacerToGrid( "HSpacer1", 0, 0 )
    submitButton = scriptDialog.AddControlToGrid( "SubmitButton", "ButtonControl", "Submit", 0, 1, expand=False )
    submitButton.ValueModified.connect(SubmitButtonPressed)
    closeButton = scriptDialog.AddControlToGrid( "CloseButton", "ButtonControl", "Close", 0, 2, expand=False )
    closeButton.ValueModified.connect(scriptDialog.closeEvent)
    scriptDialog.EndGrid()
    
    #Application Box must be listed before version box or else the application changed event will change the version
    settings = ( "DepartmentBox", "CategoryBox", "PoolBox", "SecondaryPoolBox", "GroupBox", "PriorityBox", "MachineLimitBox", "IsBlacklistBox", "MachineListBox", "LimitGroupBox", "SceneBox")
    scriptDialog.LoadSettings( GetSettingsFilename(), settings )
    scriptDialog.EnabledStickySaving( settings, GetSettingsFilename() )
    
    FileLoaded()
    scriptDialog.ShowDialog( False )
    

def ProcessOuputPath(path, frameToCompare='00', new_frame_expression='$F'):
    # Builds a dictionary from path and detects where the frame number is located
    # Regex break up path:  (?P<drive>[A-Z]:\/)(?P<path>.*\/)(?P<file>.*)(?P<ext>\..*)$
    # Regex find frames:    (?P<file>.*)(?P<frame>(?<=\D)(0*COMPAREFRAME))(?P<filecont>$|\D.*)
    # Assumption: Last group match found in filename is the frames
    
    
    regex = r'(?P<drive>[A-Z]:\/)(?P<path>.*\/)(?P<file>.*)(?P<ext>\..*)$'
    pat = re.compile(regex)
    result = pat.match(path)
    if result == None: 
        print('Regex could not detect or match ouput path')
        return 
    data = result.groupdict() 
     
    file = data['file']
    regex = r'(?P<file>.*)(?P<frame>(?<=\D)(0*' + str(frameToCompare) + r'))(?P<filecont>$|\D.*)'
    
    pat = re.compile(regex)
    result = pat.match(file)
    
    if result == None: 
        print('Regex could not detect or match frame sequence in file name\nDeadline path remapping does not work with internal USD outputs\nPlease manually set output path if needed.\n')
        return 
    
    filedata = result.groupdict() 
   
    data['padding'] = len(filedata['frame'])
    # Replace frame number with a temporary string that can be replaced later
    data['frame_holder'] = r'###frames###'
    data['file'] = filedata['file'] + data['frame_holder'] + filedata['filecont']

    # Replace temp frame holder with expression
    newFrExpr = new_frame_expression +  str(data['padding'])
    filename = str(data['file'])
    filename = filename.replace(data['frame_holder'], newFrExpr)
    data['file'] = filename
    
    #Build full output path and filename
    data['fullpath'] = data['drive'] + data['path'] + data['file'] + data['ext']

    return data


def GetSettingsFilename():
    # type: () -> str
    return os.path.join( ClientUtils.GetUsersSettingsDirectory(), "HuskSettings.ini" )

def FixPath(old_path, new_sep='/', rem_spaces=1):
    _path = old_path.replace('\\', '/')
    _path = _path.replace('\\\\', '/')
    _path = _path.replace('//', '/')

    if _path.endswith('/'):
        _path = _path[:-1]

    _path = _path.replace('/', new_sep)

    if rem_spaces:
        _path = _path.replace(' ', '_')

    new_path = _path
    return new_path
    
def FileLoaded( *args ):
    # type: (*Any) -> None
    global scriptDialog
    
    filename = scriptDialog.GetValue( "SceneBox" ).strip()
    filename = FixPath(filename, rem_spaces=0)
    stage = None
    if File.Exists(filename):
        try:
            print('loading... ' + str(filename))
            stage = Usd.Stage.Open(filename)
        except TypeError:
            print('TypeError thrown')
        except NameError:
            print('NameError thrown')
        except Exception as e:
            print('An exception occurred that was not NameError or TypeError')
            return
        print('USD file loaded')


        # Get start and end frame
        startfr = stage.GetStartTimeCode()
        endfr = stage.GetEndTimeCode()

        frameString = str(int(startfr)) + '-' + str(int(endfr))
        scriptDialog.SetValue("FramesBox", frameString)

        # Find the Rendersetting and Product primitives in USD scene
        product = None
        rendersettings = None

        for prim in stage.Traverse():
            primtype = prim.GetTypeName()
            if str(primtype) == 'RenderSettings':
                rendersettings = stage.GetPrimAtPath(prim.GetPath())
            elif str(primtype) == 'RenderProduct':
                product = stage.GetPrimAtPath(prim.GetPath())

        if product == None or rendersettings == None:
            print('Rendersettings not found in .usd file!\nCannot read complete render data from file..\n')
        
        # Get render resolution
        if rendersettings != None:
            resolution = rendersettings.GetAttribute('resolution').Get()
            scriptDialog.SetValue('WidthBox', resolution[0])
            scriptDialog.SetValue('HeightBox', resolution[1])
        
        # Get image output path
        if product != None:
            # Output image path is evaluated at given frame. ProcessOuputPath detects where the frame is in the path            
            # Will then process, detect and replace the frame number with expression
            productName = product.GetAttribute('productName').Get(int(endfr))
            outpath = FixPath(productName, rem_spaces=0)
            
            # Process path and return dictionary with useful data
            outdata = ProcessOuputPath(outpath, frameToCompare=str(int(endfr)))
            
            if outdata != None:
                outputFile = outdata['fullpath']
                #Update UI with path
                scriptDialog.SetValue('ImageOutputBox', outputFile)
        
    
def SubmitButtonPressed(*args):
   # type: (*ButtonControl) -> None
    global scriptDialog
    errors = ""
    warnings = ""

    # Check if USD files exist.
    sceneFile = scriptDialog.GetValue( "SceneBox" ).strip()
    #if not exists(sceneFile):
    #    errors += 'USD file does not exist!\n'
    tempErrors, tempWarnings = CheckFile( sceneFile, "USD", False )
    errors += tempErrors
    warnings += tempWarnings


    # Check if a valid frame range has been specified.
    frames = scriptDialog.GetValue( "FramesBox" ).strip()
    if not FrameUtils.FrameRangeValid( frames ):
        errors += 'The Frame Range "%s" is not valid.\n' % frames

    # Check the image output folder
    imageOutputDirectory = scriptDialog.GetValue( "ImageOutputBox" ).strip()
    tempErrors, tempWarnings = CheckDirectory( imageOutputDirectory, "Image Output Directory", True )
    errors += tempErrors
    warnings += tempWarnings

    concurrentTasks = scriptDialog.GetValue( "ConcurrentTasksBox" )

    # output errors , warnings
    if errors:
        scriptDialog.ShowMessageBox( "The following errors must be fixed before submitting the Husk job:\n\n%s" % errors, "Errors" )
        return
    elif warnings:
        result = scriptDialog.ShowMessageBox( "%sAre you sure you want to submit this job?" % warnings, "Warnings", ( "Yes", "No" ) )
        if result == "No":
            return

    jobName = scriptDialog.GetValue( "NameBox" )



     # Create job info file.
    jobInfoFilename = os.path.join( ClientUtils.GetDeadlineTempPath(), "husk_job_info.job" )
    writer = StreamWriter( jobInfoFilename, False, Encoding.Unicode )
    writer.WriteLine( "Plugin=Husk" )
    writer.WriteLine( "Name=%s" % jobName )
    writer.WriteLine( "Comment=%s" % scriptDialog.GetValue( "CommentBox" ) )
    writer.WriteLine( "Department=%s" % scriptDialog.GetValue( "DepartmentBox" ) )
    writer.WriteLine( "Pool=%s" % scriptDialog.GetValue( "PoolBox" ) )
    writer.WriteLine( "SecondaryPool=%s" % scriptDialog.GetValue( "SecondaryPoolBox" ) )
    writer.WriteLine( "Group=%s" % scriptDialog.GetValue( "GroupBox" ) )
    writer.WriteLine( "Priority=%s" % scriptDialog.GetValue( "PriorityBox" ) )
    writer.WriteLine( "TaskTimeoutMinutes=%s" % scriptDialog.GetValue( "TaskTimeoutBox" ) )
    writer.WriteLine( "EnableAutoTimeout=%s" % scriptDialog.GetValue( "AutoTimeoutBox" ) )
    writer.WriteLine( "ConcurrentTasks=%s" % concurrentTasks )
    writer.WriteLine( "LimitConcurrentTasksToNumberOfCpus=%s" % scriptDialog.GetValue( "LimitConcurrentTasksBox" ) )
    
    writer.WriteLine( "MachineLimit=%s" % scriptDialog.GetValue( "MachineLimitBox" ) )
    if bool( scriptDialog.GetValue( "IsBlacklistBox" ) ):
        writer.WriteLine( "Blacklist=%s" % scriptDialog.GetValue( "MachineListBox" ) )
    else:
        writer.WriteLine( "Whitelist=%s" % scriptDialog.GetValue( "MachineListBox" ) )
    
    writer.WriteLine( "LimitGroups=%s" % scriptDialog.GetValue( "LimitGroupBox" ) )
    writer.WriteLine( "JobDependencies=%s" % scriptDialog.GetValue( "DependencyBox" ) )
    writer.WriteLine( "OnJobComplete=%s" % scriptDialog.GetValue( "OnJobCompleteBox" ) )
    
    if bool( scriptDialog.GetValue( "SubmitSuspendedBox" ) ):
        writer.WriteLine( "InitialStatus=Suspended" )
    
    writer.WriteLine( "Frames=%s" % frames )
    writer.WriteLine('ChunkSize=1')

    outputDirectoryCount = 0
    if len( imageOutputDirectory ) > 0:
        writer.WriteLine('OutputDirectory%s=%s' % ( outputDirectoryCount, imageOutputDirectory ) )
        outputDirectoryCount += 1


    writer.Close()
    
    
    
    # Create plugin info file.
    pluginInfoFilename = os.path.join( ClientUtils.GetDeadlineTempPath(), 'husk_plugin_info.job')
    writer = StreamWriter( pluginInfoFilename, False, Encoding.Unicode )
    writer.WriteLine('SceneFile=%s' % sceneFile)


    if len( imageOutputDirectory ) > 0:
        writer.WriteLine( "ImageOutputDirectory=%s" % imageOutputDirectory )

    writer.WriteLine('OverrideResolution=1')
    writer.WriteLine('Width=%d' % scriptDialog.GetValue('WidthBox') )
    writer.WriteLine('Height=%d' % scriptDialog.GetValue('HeightBox') )
    #Implement this in submitter later - can be changed in job properties for now
    writer.WriteLine('LogLevel=2')

    writer.Close()
    
    # Setup the command line arguments.
    arguments = StringCollection()
    arguments.Add( jobInfoFilename )
    arguments.Add( pluginInfoFilename )
    
    # Now submit the job.
    results = ClientUtils.ExecuteCommandAndGetOutput( arguments )
    scriptDialog.ShowMessageBox( results, "Submission Results" )

def CheckFile( file, name, isOptional ):
    # type: (str, str, bool) -> Tuple[str, str]
    errors = ""
    warnings = ""

    if file:
        if not os.path.isfile( file ):
            if isOptional:
                warnings += 'The %s File "%s" does not exist.\n\n' % ( name, file )
            else:
                errors += 'The %s File "%s" does not exist.\n\n' % ( name, file )
        elif PathUtils.IsPathLocal( file ):
            warnings += 'The %s File "%s" is local.\n\n' % ( name, file )
    else:
        if not isOptional:
            errors += 'The %s File is not specified.\n\n' % name

    return errors, warnings

def CheckDirectory( folder, name, isOptional ):
    # type: (str, str, bool) -> Tuple[str, str]
    errors = ""
    warnings = ""

    if folder:
        if not os.path.isdir( folder ):
            if isOptional:
                warnings += 'The %s directory "%s" does not exist.\n\n' % ( name, folder )
            else:
                errors += 'The %s directory "%s" does not exist.\n\n' % ( name, folder )
        elif PathUtils.IsPathLocal( folder ):
            warnings += 'The %s directory "%s" is local.\n\n' % ( name, folder )
    else:
        if not isOptional:
            errors += 'The %s directory is not specified.\n\n' % name

    return errors, warnings
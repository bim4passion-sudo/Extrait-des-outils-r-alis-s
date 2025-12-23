import clr
import sys
clr.AddReference('ProtoGeometry')
from Autodesk.DesignScript.Geometry import *
from time import perf_counter as timer

#pyt_path = r'C:\Program Files (x86)\IronPython 2.7\Lib'
#sys.path.append(pyt_path)

# Import ToDSType(bool) extension method
clr.AddReference("RevitNodes")
import Revit
clr.ImportExtensions(Revit.Elements)

# Import DocumentManager and TransactionManager
clr.AddReference("RevitServices")
import RevitServices
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

# Import RevitAPI
clr.AddReference("RevitAPI")
import Autodesk
from Autodesk.Revit.DB import *

t0 = timer()

doc = DocumentManager.Instance.CurrentDBDocument
uiapp = DocumentManager.Instance.CurrentUIApplication
app = uiapp.Application
TransactionManager.Instance.EnsureInTransaction(doc)

#The inputs to this node will be stored as a list in the IN variable.
#dataEnteringNode = IN

# Constant

FT_TO_M  = 0.3048
FT_TO_MM = 304.8

#GET UI INPUTS

overwrite = IN[2]
param_source = IN[3]
param_target = IN[4]
base_on_host = IN[5]
h_tol=IN[6]/FT_TO_MM #horizontal tolerance
v_tol=IN[7]/FT_TO_MM #vertical tolerance

def str_to_list(s):
    """Convert a comma-separated string to a list of trimmed strings."""
    if not s or not s.strip():
        return []
    return [item.strip() for item in s.split(',') if item.strip()]
    
    
local_infos = str_to_list(param_source)
parameters = str_to_list(param_target)


#Coordinate of internal origin    
T = doc.ActiveProjectLocation.GetTotalTransform()  # internal -> shared 
shared_origin = T.Origin

#FUNCTIONS

def TryGetRoom(room, phase):
        try:
                inRoom = room.Room[phase]
        except:
                inRoom = None
                pass
        return inRoom


def proj_on_lvl(_element, _doc, _shared_origin, _offset=0.2):
    host_lv_id = _element.LevelId
    location = _element.Location.Point
    proj_p = None
    if host_lv_id and host_lv_id != ElementId.InvalidElementId:
        host_level = _doc.GetElement(host_lv_id)
        if isinstance(host_level, Level):
            host_el = host_level.Elevation
            proj_p = XYZ(location.X, location.Y, host_el + _shared_origin.Z + _offset)
        else:
            pass
    else :
        try:
            host = _element.Host
            host_lv_id = host.LevelId if host else None
            host_level = doc.GetElement(host_lv_id)
            if isinstance(host_level, Level):
                host_el = host_level.Elevation
            
            proj_p = XYZ(location.X, location.Y, host_el + shared_origin.Z + _offset)
        except:
            pass
         
  
    
 
        return proj_p
  


def generate_check_points(_family, h_tol=100/FT_TO_MM,v_tol=100/FT_TO_MM, include_original=False):
    """
    Generate all alternate XYZ points within horizontal (X/Y) and vertical (Z) tolerance.
    
    Args:
        pt (XYZ): Base point.
        h_tol (float): Horizontal tolerance in feet.
        v_tol (float): Vertical tolerance in feet.
        include_original (bool): Whether to include the original point (no offset).
    
    Returns:
        list[XYZ]: All tolerance-shifted XYZ points.
    """
    pt = _family.Location.Point
    offsets = [-h_tol, 0.0, h_tol]
    z_offsets = [-v_tol, 0.0, v_tol]
    alt_points = [] #check points with tolerance

    for dx in offsets:
        for dy in offsets:
            for dz in z_offsets:
                if not include_original and (dx == 0 and dy == 0 and dz == 0):
                    continue
                new_pt = XYZ(pt.X + dx, pt.Y + dy, pt.Z + dz)
                alt_points.append(new_pt)

    return [pt, alt_points]
   


def FamiliesInRoom(_room,_families, all_cp, _doc,_shared_origin, _base_on_host=True):
    outList = []
    for i_fam, family in enumerate(_families):
        #pt = family.Location.Point
        pt = all_cp[i_fam][0]
        
        if _room.IsPointInRoom(pt):
            outList.append(family)
        else:       
            
            #alt_pts = generate_tolerance_points(pt, h_tol, v_tol)
            alt_pts = all_cp[i_fam][1]
            for index, alt_loc in enumerate(alt_pts):
                if _room.IsPointInRoom(alt_loc):
                    outList.append(family)
                    break
                    
                    
            #if family not in outList: #THIS IS TIME CONSUMMING
            #    for phase in _doc.Phases:
            #        inRoom = TryGetRoom(family, phase)
            #        if inRoom != None and inRoom.Id == _room.Id:
            #            outList.append(family)
            #            break
        if _base_on_host:
            if family not in outList :
                proj_p = proj_on_lvl(family, _doc, shared_origin)
                if proj_p :
                    if _room.IsPointInRoom(proj_p):
                        outList.append(family)
                                    
    return outList




## TNG code - get elements in room ##
target_elements = []
target_elements = [UnwrapElement(IN[0][x]) for x in range(len(IN[0]))]

all_cp = []
for elem in target_elements :
    check_points = generate_check_points(elem, h_tol, h_tol)
    all_cp.append(check_points)
    
rooms = []

for room in IN[1]:
    if UnwrapElement(room).Area > 0:
        rooms.append(UnwrapElement(room))
        
el_rooms = [[] for i in range(len(rooms))]


         
try:
    errorReport = None

    for index, room in enumerate(rooms):
        el_rooms[index].extend(FamiliesInRoom(room, target_elements, all_cp, doc, shared_origin, base_on_host))
        
    
except:
    #if error accurs anywhere in the process catch it
    import traceback
    errorReport = traceback.format_exc()

    
## TNG code - copy room data to elements ##
#el_rooms = outData 
elem_id, elem_uniqueId, fam_type = {}, {}, {}
d_code_local, d_lb_local = {}, {}
elem_id, elem_uniqueId, fam_type = {}, {}, {}
d_code_local, d_lb_local = {}, {}
#local_infos = [ "Niveau", "Code local"]
#parameters = [ "TNG_ROOM_LVL", "TNG_ROOM_CODE_2"]
d_room_info = {}

for k in range(len(local_infos)) :
    info = local_infos[k]
    for i in range(len(el_rooms)):
        room_info = ""
        try:
            room_info = rooms[i].LookupParameter(info).AsString()
        except:
            pass
        
        if not room_info :
            room_info = rooms[i].LookupParameter(info).AsValueString()
            
        try:
            for elem in el_rooms[i]:
                try:
                    if overwrite:
                        elem.LookupParameter(parameters[k]).Set(str(room_info))
                    else:
                        #pass
                        if not elem.LookupParameter(parameters[k]).LookupParameter(info).AsValueString() or not elem.LookupParameter(parameters[k]).LookupParameter(info).AsValueString().strip():
                            elem.LookupParameter(parameters[k]).Set(str(room_info)) 
                                               
                        
                except:
                    elem.LookupParameter(parameters[k]).Set(str("[Error 1 : Instance parameter of element not found]"))
        except:
            elem.LookupParameter(parameters[k]).Set(str("[Error 1b : Instance parameter of element not found]"))
        #    
#export rapport de remplissage des paramètre de tous les éléments
for parameter in parameters : 
    for element in target_elements :
        try:
            if not element.LookupParameter(parameter).AsString() :
                element.LookupParameter(parameter).Set("[Waring? Outdoor element or Missing space]")
        except :
            element.LookupParameter(parameter).Set("[Error! Something is wrong]")
            
TransactionManager.Instance.TransactionTaskDone()
t1 = timer()
elap_time =  round((t1 - t0), 4)            
    
#OUT = outData    
#Assign your output to the OUT variable
if errorReport == None:
       OUT = elap_time, el_rooms
else:
       OUT = elap_time, errorReport
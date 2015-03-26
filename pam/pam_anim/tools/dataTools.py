import bpy
import bpy_extras


# TODO(SK): Missing docstring
class DataProperty(bpy.types.PropertyGroup):
    modelData = bpy.props.StringProperty(name="Model Data", subtype="FILE_PATH")
    simulationData = bpy.props.StringProperty(name="Simulation Data", subtype="FILE_PATH")


# TODO(SK): Missing docstring
class DataModelLoad(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "pam_anim.model_load"
    bl_label = "Model data"
    bl_description = "Choose Model data (as *.zip file)"

    def execute(self, context):
        bpy.context.scene.pam_anim_data.modelData = self.filepath
        return {'FINISHED'}


# TODO(SK): Missing docstring
class SimulatedModelLoad(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "pam_anim.simulated_model_load"
    bl_label = "Load simulation data"
    bl_description = "Choose Simulation data"

    def execute(self, context):
        bpy.context.scene.pam_anim_data.simulationData = self.filepath
        return {'FINISHED'}


# TODO(SK): Missing docstring
def register():
    bpy.utils.register_class(DataModelLoad)
    bpy.utils.register_class(SimulatedModelLoad)
    bpy.utils.register_class(DataProperty)
    bpy.types.Scene.pam_anim_data = bpy.props.PointerProperty(type=DataProperty)


# TODO(SK): Missing docstring
def unregister():
    del bpy.types.Scene.pam_anim_data
    bpy.utils.unregister_class(DataModelLoad)
    bpy.utils.unregister_class(SimulatedModelLoad)
    bpy.utils.unregister_class(DataProperty)

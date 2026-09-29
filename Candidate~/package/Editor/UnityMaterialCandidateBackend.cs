#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace Yukino.VRChatAgent
{
    // No global SaveAssets/Refresh/ImportAsset, no serializer-driven arbitrary setters.
    // Audited native duplicate is safe here only with an existing destination folder
    // and a closed callback inventory. Unsupported project callbacks fail closed.
    internal sealed class UnityMaterialCandidateBackend : IMaterialCandidateBackend
    {
        static void Need(bool ok,string code){if(!ok)throw new CandidateWriteDenied(code);}
        static string Digest(byte[] bytes){using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
        static string Digest(string s)=>Digest(Encoding.UTF8.GetBytes(s));
        static string Root=>Directory.GetParent(Application.dataPath).FullName;
        static string Full(string path)
        {
            MaterialCandidateGate.AssetPath(path);
            string full=Path.GetFullPath(Path.Combine(Root,path));
            Need(full.StartsWith(Path.GetFullPath(Application.dataPath)+Path.DirectorySeparatorChar,StringComparison.Ordinal),"outside_assets");
            for(string p=full;p!=Root;p=Path.GetDirectoryName(p))
                if(File.Exists(p)||Directory.Exists(p))Need((File.GetAttributes(p)&FileAttributes.ReparsePoint)==0,"reparse_unsupported");
            return full;
        }
        static string FileHash(string path,bool optional=false)
        {
            if(!File.Exists(path)){Need(optional,"file_missing");return "absent";}
            Need((File.GetAttributes(path)&FileAttributes.ReparsePoint)==0,"reparse_unsupported");
            using(var s=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read))
            {Need(s.Length<=32*1024*1024,"file_budget");using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(s)).Replace("-","").ToLowerInvariant();}
        }
        static string Memory(UnityEngine.Object obj)
        {Need(obj!=null,"missing_object");string json=EditorJsonUtility.ToJson(obj);Need(json.Length<=4*1024*1024,"memory_budget");return Digest(obj.GetType().FullName+"|"+obj.GetInstanceID()+"|"+json);}
        static void ClosedCallbacks()
        {
            // There is deliberately NO model-provided/local-checkbox bypass for this.
            // Each future known callback requires source review and dedicated tests.
            Need(!TypeCache.GetTypesDerivedFrom<AssetPostprocessor>().Any() && !TypeCache.GetTypesDerivedFrom<AssetModificationProcessor>().Any(),"unknown_asset_callbacks");
            foreach(Type type in new[]{typeof(Undo),typeof(ObjectChangeEvents),typeof(UnityEditor.SceneManagement.EditorSceneManager)})
            {
                var callbacks=type.GetFields(System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.Public|System.Reflection.BindingFlags.NonPublic).Where(f=>typeof(Delegate).IsAssignableFrom(f.FieldType)).ToArray();
                Need(callbacks.Length>0,"callback_inventory_unavailable");
                foreach(var field in callbacks)Need(field.GetValue(null)==null,"unknown_editor_callback");
            }
        }
        static Material MaterialAt(string path)
        {
            Full(path);var objects=AssetDatabase.LoadAllAssetsAtPath(path);
            Need(objects!=null && objects.Length==1 && objects[0] is Material,"standalone_material_required");
            var mat=(Material)objects[0];Need(AssetDatabase.GetAssetPath(mat)==path && mat.shader!=null,"material_identity_changed");return mat;
        }
        static string AssetState(string path,bool absentAllowed)
        {
            string full=Full(path);
            if(!File.Exists(full))
            {Need(absentAllowed && !Directory.Exists(full) && !File.Exists(full+".meta") && string.IsNullOrEmpty(AssetDatabase.AssetPathToGUID(path)),"candidate_collision");return "absent";}
            var objects=AssetDatabase.LoadAllAssetsAtPath(path);Need(objects!=null && objects.Length>0 && objects.Length<=256,"asset_evidence_missing");
            var state=new JObject{["disk"]=FileHash(full),["meta"]=FileHash(full+".meta"),["guid"]=AssetDatabase.AssetPathToGUID(path),["imported"]=AssetDatabase.GetAssetDependencyHash(path).ToString(),["memory"]=new JArray(objects.OrderBy(o=>o.GetInstanceID()).Select(Memory))};
            return Digest(state.ToString(Formatting.None));
        }
        static Renderer Host(JObject reference)
        {
            string text=(string)reference["renderer"];
            Need(GlobalObjectId.TryParse(text,out var id),"invalid_renderer_id");
            var renderer=GlobalObjectId.GlobalObjectIdentifierToObjectSlow(id) as Renderer;
            Need(renderer!=null && (renderer.GetType()==typeof(MeshRenderer) || renderer.GetType()==typeof(SkinnedMeshRenderer)),"unsupported_renderer");
            Need(GlobalObjectId.GetGlobalObjectIdSlow(renderer).ToString()==text && !EditorUtility.IsPersistent(renderer) && !PrefabUtility.IsPartOfPrefabAsset(renderer),"renderer_identity_changed");
            Need(renderer.gameObject.scene.IsValid() && renderer.gameObject.scene.isLoaded && !string.IsNullOrEmpty(renderer.gameObject.scene.path),"saved_loaded_scene_required");
            Need(renderer.gameObject.GetComponents<Renderer>().Length==1,"ambiguous_native_renderer");
            int slot=(int)reference["slot"];Need(slot>=0 && slot<renderer.sharedMaterials.Length,"invalid_slot");return renderer;
        }
        static string HostState(Renderer renderer)
        {
            string scene=Full(renderer.gameObject.scene.path);
            return Digest(Memory(renderer)+"|"+FileHash(scene)+"|"+FileHash(scene+".meta")+"|"+string.Join("|",renderer.sharedMaterials.Select(m=>m==null?"null":AssetDatabase.GetAssetPath(m))));
        }
        string operationKey;
        HashSet<string> operationDependencies;
        public JObject Capture(JObject manifest,JObject command)
        {
            ClosedCallbacks();string source=(string)manifest["source"],candidate=(string)manifest["candidate"];
            string dest=Full(candidate);Need(Directory.Exists(Path.GetDirectoryName(dest)) && AssetDatabase.IsValidFolder(Path.GetDirectoryName(candidate).Replace('\\','/')),"destination_folder_missing");
            Need(Path.GetFullPath(Directory.GetCurrentDirectory())==Path.GetFullPath(Root),"native_working_directory_mismatch");
            MaterialAt(source);
            var state=new JObject{["asset:"+source]=AssetState(source,false),["asset:"+candidate]=AssetState(candidate,true),["callback_inventory"]="no-asset-callback-types"};
            var roots=new[]{source,candidate}.Where(p=>File.Exists(Full(p))).ToArray();
            var dependencies=new HashSet<string>(StringComparer.Ordinal);
            foreach(string root in roots)
            {
                foreach(string dep in AssetDatabase.GetDependencies(root,true))dependencies.Add(dep);
                var mat=MaterialAt(root);
                foreach(string name in mat.GetTexturePropertyNames())
                {
                    var texture=mat.GetTexture(name);if(texture==null)continue;
                    string path=AssetDatabase.GetAssetPath(texture);Need(!string.IsNullOrEmpty(path),"transient_texture_unsupported");dependencies.Add(path);
                    foreach(string dep in AssetDatabase.GetDependencies(path,true))dependencies.Add(dep);
                }
                string shader=AssetDatabase.GetAssetPath(mat.shader);
                if(shader.StartsWith("Assets/",StringComparison.Ordinal))dependencies.Add(shader);
                else Need(shader=="Resources/unity_builtin_extra" || shader=="Library/unity default resources","unsupported_shader_dependency");
                state["builtin-shader:"+shader]=Memory(mat.shader);
            }
            if(command!=null && (string)command["action"]=="edit" && command["value"]?.Type==JTokenType.String)
            {string texture=MaterialCandidateGate.AssetPath(command["value"]);dependencies.Add(texture);foreach(string dep in AssetDatabase.GetDependencies(texture,true))dependencies.Add(dep);}
            // Retain pre-operation dependencies only through its postimage capture.
            // A normal plan capture drops no-longer-referenced dependencies, so unrelated
            // later texture edits do not block the task.
            if(command==null){operationKey=null;operationDependencies=null;}
            else
            {
                string key=source+"|"+candidate+"|"+command.ToString(Formatting.None);
                if(key==operationKey)dependencies.UnionWith(operationDependencies);
                operationKey=key;operationDependencies=new HashSet<string>(dependencies,StringComparer.Ordinal);
            }
            Need(dependencies.Count<=256,"dependency_budget");
            foreach(string dep in dependencies.OrderBy(s=>s,StringComparer.Ordinal))
            {
                if(dep==source || dep==candidate)continue;
                // Package/custom-importer dependencies are not silently trusted. Read-only
                // native tools remain usable while this write slice rejects them.
                Full(dep);Type type=AssetDatabase.GetMainAssetTypeAtPath(dep);
                Need(type!=null && (type==typeof(Material) || typeof(Texture).IsAssignableFrom(type) || type==typeof(Shader) || type==typeof(TextAsset) || type==typeof(DefaultAsset)),"unsupported_dependency_type");
                state["dependency:"+dep]=AssetState(dep,false);
            }
            foreach(JObject reference in (JArray)manifest["references"]){var renderer=Host(reference);state["host:"+(string)reference["renderer"]]=HostState(renderer);}
            return state;
        }
        static JObject Native(string command,JObject args)
        {
            object raw=CommandRegistry.GetHandler(command)(args);
            var result=raw as JObject ?? JObject.FromObject(raw);
            // Never forward native messages/exception objects. Gate checks result and rereads.
            return new JObject{["success"]=(bool?)result["success"]==true};
        }
        sealed class Saved
        {
            internal byte[] Disk;
            internal string Memory, Meta;
            internal bool Dirty;
            internal Material Reference;
        }
        public object Checkpoint(JObject manifest,JObject command)
        {
            if((string)command["action"]=="copy")return null;
            if((string)command["action"]=="reference")return new Saved{Reference=Host(command).sharedMaterials[(int)command["slot"]]};
            var mat=MaterialAt((string)manifest["candidate"]);string path=Full((string)manifest["candidate"]);
            FileHash(path);return new Saved{Disk=File.ReadAllBytes(path),Meta=FileHash(path+".meta"),Memory=EditorJsonUtility.ToJson(mat),Dirty=EditorUtility.IsDirty(mat)};
        }
        static void EditValue(Material mat,JObject command)
        {
            string property=(string)command["property"];Need(!string.IsNullOrEmpty(property) && property.Length<=256 && mat.HasProperty(property),"unknown_shader_property");
            var value=command["value"];Need(value!=null,"missing_value");
            if(value.Type==JTokenType.Boolean)return;
            if(value.Type==JTokenType.Float || value.Type==JTokenType.Integer){double n=(double)value;Need(!double.IsNaN(n) && !double.IsInfinity(n) && n>=-float.MaxValue && n<=float.MaxValue,"invalid_number");return;}
            if(value is JArray a){Need(a.Count>=2 && a.Count<=4,"invalid_vector");foreach(var v in a){Need(v.Type==JTokenType.Float || v.Type==JTokenType.Integer,"invalid_vector");double n=(double)v;Need(!double.IsNaN(n) && !double.IsInfinity(n) && n>=-float.MaxValue && n<=float.MaxValue,"invalid_number");}return;}
            // Strings are exact existing texture paths, never ObjectResolver instructions or JSON.
            Need(value.Type==JTokenType.String,"unsupported_value");string path=MaterialCandidateGate.AssetPath(value);Full(path);
            var tex=AssetDatabase.LoadAssetAtPath<Texture>(path);Need(tex!=null && AssetDatabase.GetAssetPath(tex)==path,"texture_missing");
        }
        public JObject Apply(JObject manifest,JObject command)
        {
            Capture(manifest,command);string action=(string)command["action"];
            if(action=="copy")
            {
                Need(!EditorUtility.IsDirty(MaterialAt((string)manifest["source"])),"unsaved_source_copy_refused");
                Need(AssetState((string)manifest["candidate"],true)=="absent","candidate_exists");
                return Native("manage_asset",new JObject{["action"]="duplicate",["path"]=manifest["source"],["destination"]=manifest["candidate"]});
            }
            if(action=="reference")
            {
                var renderer=Host(command);MaterialAt((string)manifest["candidate"]);
                var assigned=Native("manage_material",new JObject{["action"]="assign_material_to_renderer",["materialPath"]=manifest["candidate"],["target"]=renderer.gameObject.GetInstanceID().ToString(System.Globalization.CultureInfo.InvariantCulture),["searchMethod"]="by_id",["slot"]=command["slot"]});
                if((bool?)assigned["success"]==true){PrefabUtility.RecordPrefabInstancePropertyModifications(renderer);UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(renderer.gameObject.scene);}
                return assigned;
            }
            Need(action=="edit","unsupported_operation");var mat=MaterialAt((string)manifest["candidate"]);EditValue(mat,command);
            var result=Native("manage_material",new JObject{["action"]="set_material_shader_property",["materialPath"]=manifest["candidate"],["property"]=command["property"],["value"]=command["value"].DeepClone()});
            // Unlike ManageAsset.modify/CreateMaterial this does not save unrelated dirty assets,
            // nor invoke OnWillSaveAssets. Native write failure leaves unsaved state for reporting.
            if((bool?)result["success"]==true)AssetDatabase.SaveAssetIfDirty(mat);
            return result;
        }
        public JObject Read(JObject manifest)
        {
            string path=(string)manifest["candidate"];var mat=MaterialAt(path);
            object raw=CommandRegistry.GetHandler("manage_material")(new JObject{["action"]="get_material_info",["materialPath"]=path});
            var result=raw as JObject ?? JObject.FromObject(raw);
            Need((bool?)result["success"]==true && NativeReadContract.Valid("manage_material",result),"native_readback_invalid");
            return new JObject{["candidate"]=path,["fingerprint"]=AssetState(path,false),["native"]=result["data"].DeepClone(),["references"]=new JArray(((JArray)manifest["references"]).Cast<JObject>().Select(reference=>{var renderer=Host(reference);return new JObject{["renderer"]=reference["renderer"],["slot"]=reference["slot"],["material"]=AssetDatabase.GetAssetPath(renderer.sharedMaterials[(int)reference["slot"]]),["scene_dirty"]=renderer.gameObject.scene.isDirty,["scene_saved"]=false};}))};
        }
        public void Restore(JObject manifest,JObject command,object checkpoint)
        {
            ClosedCallbacks();var saved=checkpoint as Saved;Need(saved!=null,"checkpoint_missing");
            if((string)command["action"]=="reference")
            {
                var renderer=Host(command);Undo.RecordObject(renderer,"VRChat Agent explicit withdrawal");var materials=renderer.sharedMaterials;materials[(int)command["slot"]]=saved.Reference;renderer.sharedMaterials=materials;
                PrefabUtility.RecordPrefabInstancePropertyModifications(renderer);UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(renderer.gameObject.scene);return;
            }
            Need((string)command["action"]=="edit","created_candidate_retained");
            string path=Full((string)manifest["candidate"]);Need(FileHash(path+".meta")==saved.Meta,"meta_conflict");var mat=MaterialAt((string)manifest["candidate"]);
            Undo.RecordObject(mat,"VRChat Agent explicit withdrawal");
            // Only our captured standalone Material, never arbitrary caller JSON/object types.
            // Restore disk and unsaved memory separately, without global Undo or import.
            EditorJsonUtility.FromJsonOverwrite(saved.Memory,mat);File.WriteAllBytes(path,saved.Disk);
            if(saved.Dirty)EditorUtility.SetDirty(mat);else EditorUtility.ClearDirty(mat);
        }
    }
}
#endif

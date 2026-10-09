using System;
using System.Linq;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEditor;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Runtime.Helpers;
namespace MCPForUnity.Editor.Tools.Prefabs
{
    // No registry or initialization hook. Exact per-call instance; no global state.
    public sealed class CandidateScopedPrefabs
    {
        readonly Func<bool> authorized;
        bool attempted, loadStarted, unloadStarted, unloaded;
        GameObject owned;
        string exactPath,expectedGuid;
        readonly HashSet<Transform> visited=new HashSet<Transform>();
        void Visit(Transform value,int depth)
        {
            Check();
            if(value==null || depth>64 || !visited.Add(value) || visited.Count>1000 || value.childCount>1000)
                throw new InvalidOperationException("prefab_traversal_budget");
        }
        CandidateScopedPrefabs(Func<bool> authorized) { this.authorized=authorized; }
        void Check()
        {
            if(authorized==null || !authorized())throw new InvalidOperationException("prefab_authorization_changed");
            if(exactPath!=null && (expectedGuid==null || !System.Text.RegularExpressions.Regex.IsMatch(expectedGuid,@"\A[a-f0-9]{32}\z") ||
                AssetDatabase.AssetPathToGUID(exactPath)!=expectedGuid || AssetDatabase.GUIDToAssetPath(expectedGuid)!=exactPath))
                throw new InvalidOperationException("prefab_identity_changed");
        }
        GameObject LoadContents(string path)
        {
            Check();attempted=true;loadStarted=true;
            owned=PrefabUtility.LoadPrefabContents(path);
            // Do not throw between obtaining the handle and native try/finally.
            return owned;
        }
        void UnloadContents(GameObject value)
        {
            // Revocation prevents new work, not cleanup of this exact owned handle.
            if(!ReferenceEquals(value,owned))throw new InvalidOperationException("prefab_owner_mismatch");
            unloadStarted=true;PrefabUtility.UnloadPrefabContents(value);unloaded=true;
        }
        GameObject LoadAsset(string path) { Check();attempted=true;var value=AssetDatabase.LoadAssetAtPath<GameObject>(path);Check();return value; }
        static bool PathAllowed(string path) => path!=null && path.Length<=490 && path.StartsWith("Assets/",StringComparison.Ordinal) && path.EndsWith(".prefab",StringComparison.Ordinal) &&
            !path.Any(ch=>char.IsControl(ch) || "\\:%<>\"|?*".Contains(ch)) &&
            path.Split('/').All(p=>p.Length>0 && p!="." && p!=".." && p==p.Trim() && !p.EndsWith(".",StringComparison.Ordinal) &&
                !System.Text.RegularExpressions.Regex.IsMatch(p.Split('.')[0],@"\A(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])\z"));
        public static JObject Read(JObject args,Func<bool> authorized) => new CandidateScopedPrefabs(authorized).Run(args);
        JObject Run(JObject args)
        {
            string action=null;
            try
            {
                if(args==null || args.Count!=2 || args["action"]?.Type!=JTokenType.String || args["prefabPath"]?.Type!=JTokenType.String || !PathAllowed((string)args["prefabPath"]))throw new InvalidOperationException();
                action=(string)args["action"];
                if(action!="get_info" && action!="get_hierarchy")throw new InvalidOperationException();
                Check();exactPath=(string)args["prefabPath"];expectedGuid=AssetDatabase.AssetPathToGUID(exactPath);Check();
                var result=JObject.FromObject(action=="get_info" ? GetInfo(args) : GetHierarchy(args));
                Check();
                if(result["success"]?.Type!=JTokenType.Boolean || !(bool)result["success"] || !(result["data"] is JObject data))throw new InvalidOperationException();
                data["candidate_effects"]=Receipt(action);
                if(System.Text.Encoding.UTF8.GetByteCount(result.ToString(Newtonsoft.Json.Formatting.None))>262144)throw new InvalidOperationException("prefab_response_budget");
                return result;
            }
            catch
            {
                // Neither callback changes nor a failed native load are rolled back.
                return new JObject { ["success"]=false,["error"]="prefab_read_unconfirmed",["data"]=new JObject {
                    ["read_only"]=false,["effects_may_have_occurred"]=attempted,["candidate_effects"]=Receipt(action) } };
            }
        }
        JObject Receipt(string action) => new JObject {
            ["kind"]=action=="get_hierarchy" ? "prefab_contents_callbacks" : "asset_load_callbacks",
            ["version"]=1,["read_only"]=false,["all_mutations_observed"]=false,["callback_effects_path_bounded"]=false,
            ["load_started"]=loadStarted,["unload_started"]=unloadStarted,["cleanup_confirmed"]=!loadStarted || unloaded
        };
        private object GetInfo(JObject @params)
        {
            string prefabPath = @params["prefabPath"]?.ToString() ?? @params["path"]?.ToString();
            if (string.IsNullOrEmpty(prefabPath))
            {
                return new ErrorResponse("'prefabPath' parameter is required for get_info.");
            }

            string sanitizedPath = prefabPath;
            if (string.IsNullOrEmpty(sanitizedPath))
            {
                return new ErrorResponse($"Invalid prefab path: '{prefabPath}'.");
            }
            GameObject prefabAsset = LoadAsset(sanitizedPath);
            if (prefabAsset == null)
            {
                return new ErrorResponse($"No prefab asset found at path '{sanitizedPath}'.");
            }

            string guid = GetPrefabGUID(sanitizedPath);
            PrefabAssetType assetType = PrefabUtility.GetPrefabAssetType(prefabAsset);
            string prefabTypeString = assetType.ToString();
            var componentTypes = GetComponentTypeNames(prefabAsset);
            int childCount = CountChildrenRecursive(prefabAsset.transform);
            var (isVariant, parentPrefab, _) = GetVariantInfo(prefabAsset);

            return new SuccessResponse(
                $"Successfully retrieved prefab info.",
                new
                {
                    assetPath = sanitizedPath,
                    guid = guid,
                    prefabType = prefabTypeString,
                    rootObjectName = prefabAsset.name,
                    rootComponentTypes = componentTypes,
                    childCount = childCount,
                    isVariant = isVariant,
                    parentPrefab = parentPrefab
                }
            );
        }
        private object GetHierarchy(JObject @params)
        {
            string prefabPath = @params["prefabPath"]?.ToString() ?? @params["path"]?.ToString();
            if (string.IsNullOrEmpty(prefabPath))
            {
                return new ErrorResponse("'prefabPath' parameter is required for get_hierarchy.");
            }

            string sanitizedPath = prefabPath;
            if (string.IsNullOrEmpty(sanitizedPath))
            {
                return new ErrorResponse($"Invalid prefab path '{prefabPath}'. Path traversal sequences are not allowed.");
            }

            // Load prefab contents in background (without opening stage UI)
            GameObject prefabContents = LoadContents(sanitizedPath);
            if (prefabContents == null)
            {
                return new ErrorResponse($"Failed to load prefab contents from '{sanitizedPath}'.");
            }

            try
            {
                // Build complete hierarchy items (no pagination)
                var allItems = BuildHierarchyItems(prefabContents.transform, sanitizedPath);

                return new SuccessResponse(
                    $"Successfully retrieved prefab hierarchy. Found {allItems.Count} objects.",
                    new
                    {
                        prefabPath = sanitizedPath,
                        total = allItems.Count,
                        items = allItems
                    }
                );
            }
            finally
            {
                // Always unload prefab contents to free memory
                UnloadContents(prefabContents);
            }
        }
        private List<object> BuildHierarchyItems(Transform root, string mainPrefabPath)
        {
            var items = new List<object>();
            BuildHierarchyItemsRecursive(root, root, mainPrefabPath, "", items);
            return items;
        }
        private void BuildHierarchyItemsRecursive(Transform transform, Transform mainPrefabRoot, string mainPrefabPath, string parentPath, List<object> items, int depth=0)
        {
            Visit(transform,depth);

            string name = transform.gameObject.name;
            string path = string.IsNullOrEmpty(parentPath) ? name : $"{parentPath}/{name}";
            int instanceId = transform.gameObject.GetInstanceIDCompat();
            bool activeSelf = transform.gameObject.activeSelf;
            int childCount = transform.childCount;
            var componentTypes = GetComponentTypeNames(transform.gameObject);

            // Prefab information
            bool isNestedPrefab = PrefabUtility.IsAnyPrefabInstanceRoot(transform.gameObject);
            bool isPrefabRoot = transform == mainPrefabRoot;
            int nestingDepth = isPrefabRoot ? 0 : GetPrefabNestingDepth(transform.gameObject, mainPrefabRoot);
            string parentPrefabPath = isNestedPrefab && !isPrefabRoot
                ? GetParentPrefabPath(transform.gameObject, mainPrefabRoot)
                : null;
            string nestedPrefabPath = isNestedPrefab ? GetNestedPrefabPath(transform.gameObject) : null;

            var item = new
            {
                name = name,
                instanceId = instanceId,
                path = path,
                activeSelf = activeSelf,
                childCount = childCount,
                componentTypes = componentTypes,
                prefab = new
                {
                    isRoot = isPrefabRoot,
                    isNestedRoot = isNestedPrefab,
                    nestingDepth = nestingDepth,
                    assetPath = isNestedPrefab ? nestedPrefabPath : mainPrefabPath,
                    parentPath = parentPrefabPath
                }
            };

            items.Add(item);

            // Recursively process children
            foreach (Transform child in transform)
            {
                BuildHierarchyItemsRecursive(child, mainPrefabRoot, mainPrefabPath, path, items, depth+1);
            }
        }
        private string GetPrefabGUID(string assetPath)
        {
            if (string.IsNullOrEmpty(assetPath))
            {
                return null;
            }

            try
            {
                return AssetDatabase.AssetPathToGUID(assetPath);
            }
            catch { throw new InvalidOperationException("prefab_metadata_unconfirmed"); }
        }
        private (bool isVariant, string parentPath, string parentGuid) GetVariantInfo(GameObject prefabAsset)
        {
            if (prefabAsset == null)
            {
                return (false, null, null);
            }

            try
            {
                PrefabAssetType assetType = PrefabUtility.GetPrefabAssetType(prefabAsset);
                if (assetType != PrefabAssetType.Variant)
                {
                    return (false, null, null);
                }

                GameObject parentAsset = PrefabUtility.GetCorrespondingObjectFromSource(prefabAsset);
                if (parentAsset == null)
                {
                    throw new InvalidOperationException("prefab_parent_unresolved");
                }

                string parentPath = AssetDatabase.GetAssetPath(parentAsset);
                string parentGuid = GetPrefabGUID(parentPath);

                return (true, parentPath, parentGuid);
            }
            catch { throw new InvalidOperationException("prefab_metadata_unconfirmed"); }
        }
        private List<string> GetComponentTypeNames(GameObject obj)
        {
            var typeNames = new List<string>();

            if (obj == null)
            {
                return typeNames;
            }

            try
            {
                Check();var components = obj.GetComponents<Component>();Check();
                if(components==null || components.Length>256 || components.Any(x=>x==null))throw new InvalidOperationException("prefab_components_incomplete");
                foreach (var component in components)
                {
                    if (component != null)
                    {
                        typeNames.Add(component.GetType().FullName);
                    }
                }
            }
            catch { throw new InvalidOperationException("prefab_metadata_unconfirmed"); }

            return typeNames;
        }
        private int CountChildrenRecursive(Transform transform, int depth=0)
        {
            Visit(transform,depth);
            if (transform == null)
            {
                return 0;
            }

            int count = transform.childCount;
            for (int i = 0; i < transform.childCount; i++)
            {
                count += CountChildrenRecursive(transform.GetChild(i),depth+1);
            }
            return count;
        }
        private string GetNestedPrefabPath(GameObject gameObject)
        {
            if (gameObject == null || !PrefabUtility.IsAnyPrefabInstanceRoot(gameObject))
            {
                return null;
            }

            try
            {
                Check();var sourcePrefab = PrefabUtility.GetCorrespondingObjectFromSource(gameObject);Check();
                if(sourcePrefab==null)throw new InvalidOperationException("prefab_nested_unresolved");
                if (sourcePrefab != null)
                {
                    return AssetDatabase.GetAssetPath(sourcePrefab);
                }
            }
            catch { throw new InvalidOperationException("prefab_metadata_unconfirmed"); }

            return null;
        }
        private int GetPrefabNestingDepth(GameObject gameObject, Transform mainPrefabRoot)
        {
            if (gameObject == null)
                return -1;

            // Main prefab root
            if (gameObject.transform == mainPrefabRoot)
                return 0;

            // Not a prefab instance root
            if (!PrefabUtility.IsAnyPrefabInstanceRoot(gameObject))
                return -1;

            // Calculate depth by walking up the hierarchy
            int depth = 0;
            Transform current = gameObject.transform;

            while (current != null && current != mainPrefabRoot)
            {
                if (PrefabUtility.IsAnyPrefabInstanceRoot(current.gameObject))
                {
                    depth++;
                }
                current = current.parent;
            }

            return depth;
        }
        private string GetParentPrefabPath(GameObject gameObject, Transform mainPrefabRoot)
        {
            if (gameObject == null || gameObject.transform == mainPrefabRoot)
                return null;

            if (!PrefabUtility.IsAnyPrefabInstanceRoot(gameObject))
                return null;

            // Walk up the hierarchy to find the parent prefab instance
            Transform current = gameObject.transform.parent;

            while (current != null && current != mainPrefabRoot)
            {
                if (PrefabUtility.IsAnyPrefabInstanceRoot(current.gameObject))
                {
                    return GetNestedPrefabPath(current.gameObject);
                }
                current = current.parent;
            }

            // Parent is the main prefab root - get its asset path
            if (mainPrefabRoot != null)
            {
                return AssetDatabase.GetAssetPath(mainPrefabRoot.gameObject);
            }

            return null;
        }
    }
}

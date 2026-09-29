// TEST ONLY: byte-exact selected methods from pinned Coplay v10.2.0.
/*
MIT License

Copyright (c) 2025 CoplayDev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
// Not the entire native assembly; Unity and unused helper APIs remain explicit doubles.
// Upstream MIT license: https://github.com/CoplayDev/unity-mcp/blob/30d22075093d1d35dfb0091c1c7550e9ad948577/LICENSE
using System;using System.IO;using System.Collections.Generic;using Newtonsoft.Json.Linq;using UnityEngine;using UnityEditor;using MCPForUnity.Editor.Helpers;
static class WritePinnedMaterial {
        private static string NormalizePath(string path)
        {
            if (string.IsNullOrEmpty(path)) return path;

            // Normalize separators and ensure Assets/ root
            path = AssetPathUtility.SanitizeAssetPath(path);

            // Ensure .mat extension
            if (!path.EndsWith(".mat", StringComparison.OrdinalIgnoreCase))
            {
                path += ".mat";
            }

            return path;
        }
        private static object SetMaterialShaderProperty(JObject @params)
        {
            string materialPath = NormalizePath(@params["materialPath"]?.ToString());
            string property = @params["property"]?.ToString();
            JToken value = @params["value"];

            if (string.IsNullOrEmpty(materialPath) || string.IsNullOrEmpty(property) || value == null)
            {
                return new ErrorResponse("materialPath, property, and value are required");
            }

            // Find material
            var findInstruction = new JObject { ["find"] = materialPath };
            Material mat = ObjectResolver.Resolve(findInstruction, typeof(Material)) as Material;

            if (mat == null)
            {
                return new ErrorResponse($"Could not find material at path: {materialPath}");
            }

            Undo.RecordObject(mat, "Set Material Property");

            // Normalize alias/casing once for all code paths
            property = MaterialOps.ResolvePropertyName(mat, property);

            // 1. Try handling Texture instruction explicitly (ManageMaterial special feature)
            if (value.Type == JTokenType.Object)
            {
                // Check if it looks like an instruction
                if (value is JObject obj && (obj.ContainsKey("find") || obj.ContainsKey("method")))
                {
                    Texture tex = ObjectResolver.Resolve(obj, typeof(Texture)) as Texture;
                    if (tex != null && mat.HasProperty(property))
                    {
                        mat.SetTexture(property, tex);
                        EditorUtility.SetDirty(mat);
                        return new SuccessResponse($"Set texture property {property} on {mat.name}");
                    }
                }
            }

            // 2. Fallback to standard logic via MaterialOps (handles Colors, Floats, Strings->Path)
            bool success = MaterialOps.TrySetShaderProperty(mat, property, value, UnityJsonSerializer.Instance);

            if (success)
            {
                EditorUtility.SetDirty(mat);
                return new SuccessResponse($"Set property {property} on {mat.name}");
            }
            else
            {
                return new ErrorResponse($"Failed to set property {property}. Value format might be unsupported or texture not found.");
            }
        }
        private static object AssignMaterialToRenderer(JObject @params)
        {
            string target = @params["target"]?.ToString();
            string searchMethod = @params["searchMethod"]?.ToString();
            string materialPath = NormalizePath(@params["materialPath"]?.ToString());
            int slot = @params["slot"]?.ToObject<int>() ?? 0;

            if (string.IsNullOrEmpty(target) || string.IsNullOrEmpty(materialPath))
            {
                return new ErrorResponse("target and materialPath are required");
            }

            var goInstruction = new JObject { ["find"] = target };
            if (!string.IsNullOrEmpty(searchMethod)) goInstruction["method"] = searchMethod;

            GameObject go = ObjectResolver.Resolve(goInstruction, typeof(GameObject)) as GameObject;
            if (go == null)
            {
                return new ErrorResponse($"Could not find target GameObject: {target}");
            }

            Renderer renderer = go.GetComponent<Renderer>();
            if (renderer == null)
            {
                return new ErrorResponse($"GameObject {go.name} has no Renderer component");
            }

            var matInstruction = new JObject { ["find"] = materialPath };
            Material mat = ObjectResolver.Resolve(matInstruction, typeof(Material)) as Material;
            if (mat == null)
            {
                return new ErrorResponse($"Could not find material: {materialPath}");
            }

            Undo.RecordObject(renderer, "Assign Material");

            Material[] sharedMats = renderer.sharedMaterials;
            if (slot < 0 || slot >= sharedMats.Length)
            {
                return new ErrorResponse($"Slot {slot} out of bounds (count: {sharedMats.Length})");
            }

            sharedMats[slot] = mat;
            renderer.sharedMaterials = sharedMats;

            EditorUtility.SetDirty(renderer);
            return new SuccessResponse($"Assigned material {mat.name} to {go.name} slot {slot}");
        }
        private static object GetMaterialInfo(JObject @params)
        {
            string materialPath = NormalizePath(@params["materialPath"]?.ToString());
            if (string.IsNullOrEmpty(materialPath))
            {
                return new ErrorResponse("materialPath is required");
            }

            var findInstruction = new JObject { ["find"] = materialPath };
            Material mat = ObjectResolver.Resolve(findInstruction, typeof(Material)) as Material;

            if (mat == null)
            {
                return new ErrorResponse($"Could not find material at path: {materialPath}");
            }

            Shader shader = mat.shader;
            var properties = new List<object>();

#if UNITY_6000_0_OR_NEWER
            int propertyCount = shader.GetPropertyCount();
            for (int i = 0; i < propertyCount; i++)
            {
                string name = shader.GetPropertyName(i);
                var type = shader.GetPropertyType(i);
                string description = shader.GetPropertyDescription(i);

                object currentValue = null;
                try
                {
                    if (mat.HasProperty(name))
                    {
                        switch (type)
                        {
                            case UnityEngine.Rendering.ShaderPropertyType.Color:
                                var c = mat.GetColor(name);
                                currentValue = new { r = c.r, g = c.g, b = c.b, a = c.a };
                                break;
                            case UnityEngine.Rendering.ShaderPropertyType.Vector:
                                var v = mat.GetVector(name);
                                currentValue = new { x = v.x, y = v.y, z = v.z, w = v.w };
                                break;
                            case UnityEngine.Rendering.ShaderPropertyType.Float:
                            case UnityEngine.Rendering.ShaderPropertyType.Range:
                                currentValue = mat.GetFloat(name);
                                break;
                            case UnityEngine.Rendering.ShaderPropertyType.Texture:
                                currentValue = mat.GetTexture(name)?.name ?? "null";
                                break;
                        }
                    }
                }
                catch (Exception ex)
                {
                    currentValue = $"<error: {ex.Message}>";
                }

                properties.Add(new
                {
                    name = name,
                    type = type.ToString(),
                    description = description,
                    value = currentValue
                });
            }
#else
            int propertyCount = ShaderUtil.GetPropertyCount(shader);
            for (int i = 0; i < propertyCount; i++)
            {
                string name = ShaderUtil.GetPropertyName(shader, i);
                ShaderUtil.ShaderPropertyType type = ShaderUtil.GetPropertyType(shader, i);
                string description = ShaderUtil.GetPropertyDescription(shader, i);

                object currentValue = null;
                try
                {
                    if (mat.HasProperty(name))
                    {
                        switch (type)
                        {
                            case ShaderUtil.ShaderPropertyType.Color:
                                var c = mat.GetColor(name);
                                currentValue = new { r = c.r, g = c.g, b = c.b, a = c.a };
                                break;
                            case ShaderUtil.ShaderPropertyType.Vector:
                                var v = mat.GetVector(name);
                                currentValue = new { x = v.x, y = v.y, z = v.z, w = v.w };
                                break;
                            case ShaderUtil.ShaderPropertyType.Float: currentValue = mat.GetFloat(name); break;
                            case ShaderUtil.ShaderPropertyType.Range: currentValue = mat.GetFloat(name); break;
                            case ShaderUtil.ShaderPropertyType.TexEnv: currentValue = mat.GetTexture(name)?.name ?? "null"; break;
                        }
                    }
                }
                catch (Exception ex)
                {
                    currentValue = $"<error: {ex.Message}>";
                }

                properties.Add(new
                {
                    name = name,
                    type = type.ToString(),
                    description = description,
                    value = currentValue
                });
            }
#endif

            return new SuccessResponse($"Retrieved material info for {mat.name}", new
            {
                material = mat.name,
                shader = shader.name,
                properties = properties
            });
        }
}
static class WritePinnedAsset {
        private static object DuplicateAsset(string path, string destinationPath)
        {
            if (string.IsNullOrEmpty(path))
                return new ErrorResponse("'path' is required for duplicate.");

            string sourcePath = AssetPathUtility.SanitizeAssetPath(path);
            if (!AssetExists(sourcePath))
                return new ErrorResponse($"Source asset not found at path: {sourcePath}");

            string destPath;
            if (string.IsNullOrEmpty(destinationPath))
            {
                // Generate a unique path if destination is not provided
                destPath = AssetDatabase.GenerateUniqueAssetPath(sourcePath);
            }
            else
            {
                destPath = AssetPathUtility.SanitizeAssetPath(destinationPath);
                if (AssetExists(destPath))
                    return new ErrorResponse($"Asset already exists at destination path: {destPath}");
                // Ensure destination directory exists
                EnsureDirectoryExists(Path.GetDirectoryName(destPath));
            }

            try
            {
                bool success = AssetDatabase.CopyAsset(sourcePath, destPath);
                if (success)
                {
                    // AssetDatabase.Refresh();
                    return new SuccessResponse(
                        $"Asset '{sourcePath}' duplicated to '{destPath}'.",
                        GetAssetData(destPath)
                    );
                }
                else
                {
                    return new ErrorResponse(
                        $"Failed to duplicate asset from '{sourcePath}' to '{destPath}'."
                    );
                }
            }
            catch (Exception e)
            {
                return new ErrorResponse($"Error duplicating asset '{sourcePath}': {e.Message}");
            }
        }
        private static void EnsureDirectoryExists(string directoryPath)
        {
            if (string.IsNullOrEmpty(directoryPath))
                return;
            string fullDirPath = Path.Combine(Directory.GetCurrentDirectory(), directoryPath);
            if (!Directory.Exists(fullDirPath))
            {
                Directory.CreateDirectory(fullDirPath);
                AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport); // Let Unity know about the new folder
            }
        }
        private static bool AssetExists(string sanitizedPath)
        {
            // AssetDatabase APIs are generally preferred over raw File/Directory checks for assets.
            // Check if it's a known asset GUID.
            if (!string.IsNullOrEmpty(AssetDatabase.AssetPathToGUID(sanitizedPath)))
            {
                return true;
            }
            // AssetPathToGUID might not work for newly created folders not yet refreshed.
            // Check directory explicitly for folders.
            if (Directory.Exists(Path.Combine(Directory.GetCurrentDirectory(), sanitizedPath)))
            {
                // Check if it's considered a *valid* folder by Unity
                return AssetDatabase.IsValidFolder(sanitizedPath);
            }
            // Check file existence for non-folder assets.
            if (File.Exists(Path.Combine(Directory.GetCurrentDirectory(), sanitizedPath)))
            {
                return true; // Assume if file exists, it's an asset or will be imported
            }

            return false;
            // Alternative: return !string.IsNullOrEmpty(AssetDatabase.AssetPathToGUID(sanitizedPath));
        }
private static object GetAssetData(string path)=>new {path}; // metadata fixture, preview forbidden
}

// Derived from pinned Coplay ManageAsset. See PROVENANCE.json and LICENSE.md.
// Additive helper only: no registration, no startup hooks, no permission grant.
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Globalization;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEditor;
using MCPForUnity.Editor.Helpers;
namespace MCPForUnity.Editor.Tools
{
    public static class CandidateScopedAssets
    {
        private static object SearchAssets(JObject @params, Func<bool> authorized)
        {
            string searchPattern = @params["searchPattern"]?.ToString();
            string filterType = @params["filterType"]?.ToString();
            string pathScope = @params["path"]?.ToString(); // Use path as folder scope
            string filterDateAfterStr = @params["filterDateAfter"]?.ToString();
            int pageSize = @params["pageSize"]?.ToObject<int?>() ?? 50; // Default page size
            int pageNumber = @params["pageNumber"]?.ToObject<int?>() ?? 1; // Default page number (1-based)
            bool generatePreview = @params["generatePreview"]?.ToObject<bool>() ?? false;

            List<string> searchFilters = new List<string>();
            if (!string.IsNullOrEmpty(searchPattern))
                searchFilters.Add(searchPattern);
            if (!string.IsNullOrEmpty(filterType))
                searchFilters.Add($"t:{filterType}");

            string[] folderScope = null;
            if (!string.IsNullOrEmpty(pathScope))
            {
                folderScope = new string[] { AssetPathUtility.SanitizeAssetPath(pathScope) };
                if (!AssetDatabase.IsValidFolder(folderScope[0]))
                {
                    // Maybe the user provided a file path instead of a folder?
                    // We could search in the containing folder, or return an error.
                    return new ErrorResponse("asset_scope_invalid");
                }
            }

            DateTime? filterDateAfter = null;
            if (!string.IsNullOrEmpty(filterDateAfterStr))
            {
                if (
                    DateTime.TryParse(
                        filterDateAfterStr,
                        CultureInfo.InvariantCulture,
                        DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                        out DateTime parsedDate
                    )
                )
                {
                    filterDateAfter = parsedDate;
                }
                else
                {
                    McpLog.Warn(
                        $"Could not parse filterDateAfter: '{filterDateAfterStr}'. Expected ISO 8601 format."
                    );
                }
            }

            try
            {
                string[] guids = AssetDatabase.FindAssets(
                    string.Join(" ", searchFilters),
                    folderScope
                );
                if (guids == null || guids.Length > 4096) return new ErrorResponse("asset_match_budget");
                List<string> paths = new List<string>();
                int totalFound = 0;
                var seenPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                var resolvedGuids = new Dictionary<string,string>(StringComparer.Ordinal);

                foreach (string guid in guids)
                {
                    string assetPath = AssetDatabase.GUIDToAssetPath(guid);
                    if (!PathAllowed(assetPath) || !assetPath.StartsWith(pathScope + "/", StringComparison.Ordinal) || !seenPaths.Add(assetPath))
                        return new ErrorResponse("asset_resolution_changed");
                    resolvedGuids.Add(assetPath,guid);

                    // Apply date filter if present
                    if (filterDateAfter.HasValue)
                    {
                        DateTime lastWriteTime = File.GetLastWriteTimeUtc(
                            Path.Combine(Directory.GetCurrentDirectory(), assetPath)
                        );
                        if (lastWriteTime <= filterDateAfter.Value)
                        {
                            continue; // Skip assets older than or equal to the filter date
                        }
                    }

                    totalFound++; // Count matching assets before pagination
                    paths.Add(assetPath);
                }

                // Apply pagination
                int startIndex = (pageNumber - 1) * pageSize;
                var pagedResults = new List<object>();
                foreach (string selected in paths.Skip(startIndex).Take(pageSize))
                {
                    if (!authorized()) return new ErrorResponse("asset_authorization_revoked; effects_may_have_occurred=true");
                    string expectedGuid = resolvedGuids[selected];
                    if (AssetDatabase.GUIDToAssetPath(expectedGuid) != selected || AssetDatabase.AssetPathToGUID(selected) != expectedGuid)
                        return new ErrorResponse("asset_identity_changed; effects_may_have_occurred=true");
                    var row = GetAssetData(selected, false);
                    if (AssetDatabase.GUIDToAssetPath(expectedGuid) != selected || AssetDatabase.AssetPathToGUID(selected) != expectedGuid)
                        return new ErrorResponse("asset_identity_changed; effects_may_have_occurred=true");
                    if (!authorized()) return new ErrorResponse("asset_authorization_revoked; effects_may_have_occurred=true");
                    pagedResults.Add(row);
                }
                if (!authorized()) return new ErrorResponse("asset_authorization_revoked; effects_may_have_occurred=true");

                return new SuccessResponse(
                    $"Found {totalFound} asset(s). Returning page {pageNumber} ({pagedResults.Count} assets).",
                    new
                    {
                        totalAssets = totalFound,
                        pageSize = pageSize,
                        pageNumber = pageNumber,
                        assets = pagedResults,
                    }
                );
            }
            catch (Exception)
            {
                return new ErrorResponse("asset_read_failed; effects_may_have_occurred=true");
            }
        }
        private static object GetAssetInfo(string path, bool generatePreview)
        {
            if (string.IsNullOrEmpty(path))
                return new ErrorResponse("'path' is required for get_info.");
            string fullPath = AssetPathUtility.SanitizeAssetPath(path);
            if (!AssetExists(fullPath))
                return new ErrorResponse($"Asset not found at path: {fullPath}");

            try
            {
                return new SuccessResponse(
                    "Asset info retrieved.",
                    GetAssetData(fullPath, generatePreview)
                );
            }
            catch (Exception e)
            {
                return new ErrorResponse($"Error getting info for asset '{fullPath}': {e.Message}");
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
        private static object GetAssetData(string path, bool generatePreview = false)
        {
            if (string.IsNullOrEmpty(path) || !AssetExists(path))
                return null;

            string guid = AssetDatabase.AssetPathToGUID(path);
            Type assetType = AssetDatabase.GetMainAssetTypeAtPath(path);
            UnityEngine.Object asset = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(path);
            string previewBase64 = null;
            int previewWidth = 0;
            int previewHeight = 0;

            if (generatePreview && asset != null)
            {
                Texture2D preview = AssetPreview.GetAssetPreview(asset);

                if (preview != null)
                {
                    try
                    {
                        // Ensure texture is readable for EncodeToPNG
                        // Creating a temporary readable copy is safer
                        RenderTexture rt = null;
                        Texture2D readablePreview = null;
                        RenderTexture previous = RenderTexture.active;
                        try
                        {
                            rt = RenderTexture.GetTemporary(preview.width, preview.height);
                            UnityEngine.Graphics.Blit(preview, rt);
                            RenderTexture.active = rt;
                            readablePreview = new Texture2D(preview.width, preview.height, TextureFormat.RGB24, false);
                            readablePreview.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
                            readablePreview.Apply();

                            var pngData = readablePreview.EncodeToPNG();
                            if (pngData != null && pngData.Length > 0)
                            {
                                previewBase64 = Convert.ToBase64String(pngData);
                                previewWidth = readablePreview.width;
                                previewHeight = readablePreview.height;
                            }
                        }
                        finally
                        {
                            RenderTexture.active = previous;
                            if (rt != null) RenderTexture.ReleaseTemporary(rt);
                            if (readablePreview != null) UnityEngine.Object.DestroyImmediate(readablePreview);
                        }
                    }
                    catch (Exception ex)
                    {
                        McpLog.Warn(
                            $"Failed to generate readable preview for '{path}': {ex.Message}. Preview might not be readable."
                        );
                        // Fallback: Try getting static preview if available?
                        // Texture2D staticPreview = AssetPreview.GetMiniThumbnail(asset);
                    }
                }
                else
                {
                    McpLog.Warn(
                        $"Could not get asset preview for {path} (Type: {assetType?.Name}). Is it supported?"
                    );
                }
            }

            return new
            {
                path = path,
                guid = guid,
                assetType = assetType?.FullName ?? "Unknown",
                name = Path.GetFileNameWithoutExtension(path),
                fileName = Path.GetFileName(path),
                isFolder = AssetDatabase.IsValidFolder(path),
                instanceID = asset?.GetInstanceIDCompat() ?? 0,
                lastWriteTimeUtc = File.GetLastWriteTimeUtc(
                        Path.Combine(Directory.GetCurrentDirectory(), path)
                    )
                    .ToString("o"), // ISO 8601
                // --- Preview Data ---
                previewBase64 = previewBase64, // PNG data as Base64 string
                previewWidth = previewWidth,
                previewHeight = previewHeight,
                // TODO: Add more metadata? Importer settings? Dependencies?
            };
        }
        static bool PathAllowed(string path) => path != null && path.Length <= 512 &&
            path.StartsWith("Assets/", StringComparison.Ordinal) && !path.Any(char.IsControl) &&
            path.IndexOfAny(new[] { (char)92, ':', '*', '?', '"', '<', '>', '|', '%' }) < 0 &&
            path.Split('/').All(p => p.Length > 0 && p != "." && p != ".." && p.Trim() == p && !p.EndsWith(".", StringComparison.Ordinal));
        static bool Integer(JToken value, int max) => value != null && value.Type == JTokenType.Integer &&
            (decimal)value >= 1 && (decimal)value <= max;
        public static object Query(JObject args, Func<bool> authorized = null)
        {
            if (authorized == null || !authorized()) return new ErrorResponse("asset_callbacks_not_authorized");
            string[] keys = { "path", "pageNumber", "pageSize", "generatePreview", "searchPattern", "filterType", "filterDateAfter" };
            if (args == null || args.Properties().Any(p => !keys.Contains(p.Name)) ||
                args["path"]?.Type != JTokenType.String || !PathAllowed((string)args["path"]) ||
                !Integer(args["pageNumber"], 1000000) || !Integer(args["pageSize"], 50) ||
                args["generatePreview"]?.Type != JTokenType.Boolean || (bool)args["generatePreview"] ||
                new[] { "searchPattern", "filterType", "filterDateAfter" }.Any(k => args[k] != null &&
                    (args[k].Type != JTokenType.String || ((string)args[k]).Length > 128 || ((string)args[k]).Any(char.IsControl))))
                return new ErrorResponse("asset_params_invalid");
            string date = (string)args["filterDateAfter"];
            if (!string.IsNullOrEmpty(date) && !DateTime.TryParse(date, CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out _))
                return new ErrorResponse("asset_date_invalid");
            return SearchAssets(args, authorized);
        }
        public static object Info(string path, Func<bool> authorized = null)
        {
            if (authorized == null || !authorized()) return new ErrorResponse("asset_callbacks_not_authorized");
            if (!PathAllowed(path)) return new ErrorResponse("asset_path_invalid");
            string expectedGuid = AssetDatabase.AssetPathToGUID(path);
            if (string.IsNullOrEmpty(expectedGuid) || AssetDatabase.GUIDToAssetPath(expectedGuid) != path)
                return new ErrorResponse("asset_identity_unavailable");
            var result = GetAssetInfo(path, false);
            if (AssetDatabase.GUIDToAssetPath(expectedGuid) != path || AssetDatabase.AssetPathToGUID(path) != expectedGuid)
                return new ErrorResponse("asset_identity_changed; effects_may_have_occurred=true");
            if (!(result is SuccessResponse)) return new ErrorResponse("asset_read_failed; effects_may_have_occurred=true");
            return authorized() ? result : new ErrorResponse("asset_authorization_revoked; effects_may_have_occurred=true");
        }
    }
}

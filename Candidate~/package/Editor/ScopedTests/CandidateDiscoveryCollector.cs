using System;
using System.Collections.Generic;
using NUnit.Framework.Interfaces;
namespace UnityEditor.TestTools.TestRunner { public sealed partial class CandidateDiscoveryJob {
        private void CollectFromNode(
            ITest node,
            string mode,
            List<Dictionary<string, string>> output,
            HashSet<string> seen,
            List<string> path, int depth=0)
        {
            if (node == null)throw new InvalidOperationException("discovery_incomplete");

            if(!Allowed() || depth>64 || ++visited>4096)throw new InvalidOperationException("discovery_depth_budget");
            bool hasName = !string.IsNullOrEmpty(node.Name);
            if (hasName)
            {
                path.Add(node.Name);
            }

            bool hasChildren = node.Tests.Count > 0 && node.Tests != null;

            if (!hasChildren && !node.IsSuite)
            {
                string fullName = string.IsNullOrEmpty(node.FullName) ? node.Name ?? string.Empty : node.FullName;
                string key = $"{mode}:{fullName}";

                if (string.IsNullOrEmpty(fullName) || !seen.Add(key))throw new InvalidOperationException("discovery_incomplete");
                else
                {
                    string computedPath = path.Count > 0 ? string.Join("/", path) : fullName;
                    output.Add(new Dictionary<string, string>
                    {
                        ["name"] = node.Name ?? fullName,
                        ["full_name"] = fullName,
                        ["path"] = computedPath,
                        ["mode"] = mode.ToString(),
                    });
                }
            }
            else if (node.Tests != null)
            {
                foreach (var child in node.Tests)
                {
                    CollectFromNode(child, mode, output, seen, path, depth+1);
                }
            }

            if (hasName && path.Count > 0)
            {
                path.RemoveAt(path.Count - 1);
            }
        }
}}

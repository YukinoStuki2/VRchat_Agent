"""Source-boundary tests; do not claim these execute a Unity Editor."""
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'Packages~' / 'com.yukino.vrchat-managed-editing'

def read(name):
    p = PKG / 'Editor' / name
    assert p.is_file(), f'missing managed editor implementation: {name}'
    return p.read_text()

def test_no_remote_grant_and_exact_tool_surface():
    s = read('ManagedTools.cs')
    names = re.findall(r'\[McpForUnityTool\("([^"]+)"', s)
    assert len(names) == len(set(names)) == 5
    assert set(names) == {'vrchat_me_status','vrchat_me_plan','vrchat_me_preview','vrchat_me_apply','vrchat_me_rollback'}
    assert 'GrantLocally(' not in s
    assert 'GetMethod(' not in s and 'Invoke(' not in s

def test_batch_validation_precedes_undo_and_scoped_writer():
    s = read('ManagedSession.cs')
    apply = s[s.index('internal static JObject Apply('):s.index('internal static JObject Rollback(')]
    assert apply.index('ValidateCurrent') < apply.index('WriteTransaction(')
    assert apply.index('Gate.Demand(') < apply.index('WriteTransaction(')
    assert 'FindBlendShapePartial' not in s
    assert 'SaveAssets(' not in s and 'SaveScene(' not in s and 'ApplyPrefabInstance(' not in s
    assert 'SetBlendShapeWeight' in s

def test_lifecycle_and_main_thread_gates():
    s = read('ManagedSession.cs')
    for term in ['beforeAssemblyReload','playModeStateChanged','sceneOpened','sceneClosing','sceneSaving','quitting','isCompiling','isUpdating','isPlayingOrWillChangePlaymode','InAnimationMode','IsPreviewScene','ManagedThreadId']:
        assert term in s
    assert 'ManagedWindow.TransportAcknowledged' in s
    assert 'ManagedWindow.IsLocalWindowOpen' in s
    assert 'ManagedWindow.CheckpointAcknowledged' in s
    assert 'nextIdentityCheck' in s  # bounded idle polling; each write still checks synchronously
    assert 'IsPreviewScene(scene)' in s  # owned preview scene lifecycle must not revoke source lease
    assert 'internal static string LastApplySummary' in s

def test_active_and_new_scene_lifecycle_revoke_except_owned_preview():
    s = read('ManagedSession.cs')
    active = re.search(r'EditorSceneManager\.activeSceneChangedInEditMode\s*\+=([^;]+Revoke\(\);[^\n]+)', s)
    assert active, 'switching between already-loaded scenes must revoke'
    assert 'IsPreviewScene(previous)' in active[1] and 'IsPreviewScene(next)' in active[1]
    created = re.search(r'EditorSceneManager\.newSceneCreated\s*\+=([^;]+Revoke\(\);[^\n]+)', s)
    assert created, 'creating a new authoring scene must revoke'
    assert 'IsPreviewScene(scene)' in created[1]

def test_restore_conflict_and_no_reset_all():
    s = read('ManagedSession.cs')
    restore = s[s.index('internal static JObject RollbackLocally('):s.index('private static void WriteTransaction(')]
    assert 'ValidateCurrent' in restore and 'true' in restore
    assert 'GetBlendShapeIndex(delta.Name)' in s
    assert 'SetBlendShapeWeight(i, 0' not in s

def test_mesh_boundary_rejects_untracked_geometry_and_versions_imports():
    s = read('ManagedSession.cs')
    validate = s[s.index('private static void ValidateSource('):s.index('private static string TargetKey(')]
    assert 'ValidateMeshAsset(renderer.sharedMesh)' in validate
    assert 'internal static string ValidateMeshAsset(Mesh mesh)' in s
    for required in ['EditorUtility.IsPersistent(mesh)', 'AssetDatabase.IsSubAsset(mesh)',
                     'ModelImporter', 'EditorUtility.IsDirty(mesh)', 'mesh.hideFlags',
                     'EditorUtility.IsDirty(importer)', 'EditorUtility.IsDirty(mainAsset)',
                     'UNTRACKED_MESH', 'DIRTY_MESH']:
        assert required in s
    key = s[s.index('private static string MeshKey('):s.index('private static string Digest(')]
    assert 'ValidateMeshAsset(mesh)' in key
    assert 'EditorUtility.GetDirtyCount(mesh)' in key
    assert 'EditorUtility.GetDirtyCount(importer)' in key
    assert 'assetRevision' in key
    assert 'OnPostprocessAllAssets' in s and 'ManagedSession.AssetsChanged()' in s
    changed = s[s.index('internal static void AssetsChanged()'):s.index('private static void Tick()')]
    assert 'assetRevision++' in changed and 'Revoke()' in changed
    for full_mesh_read in ['mesh.vertices', 'mesh.bindposes', 'GetBlendShapeFrameVertices', 'GetVertices(']:
        assert full_mesh_read not in s, 'idle validation must not read gigabytes of mesh samples'

def test_documented_imported_mesh_boundary_and_fresh_project_dependencies():
    text = (PKG / 'README.md').read_text()
    for required in ['ModelImporter', 'GetDirtyCount', 'not a full native mesh content hash',
                     'revoke first', 'v0.1.1', '12', '17']:
        assert required in text
    assert 'https://github.com/YukinoStuki2/VRchat_Agent.git#v0.1.1' in text

def test_error_permission_metadata_compares_before_and_after_lease():
    s = read('ManagedTools.cs')
    run = s[s.index('internal static object Run('):s.index('private static JObject Error(')]
    assert 'bool wasActive = ManagedSession.Gate.Active;' in run
    assert 'string previousLease = ManagedSession.Gate.LeaseId;' in run
    assert run.index('previousLease =') < run.index('action()')
    assert 'wasActive != active || previousLease != ManagedSession.Gate.LeaseId' in run
    assert '["active"] = active' in run
    assert '["permission_changed"]' in run
    assert run.index('["permission_changed"]') > run.index('catch (Exception e)')
    error = s[s.index('private static JObject Error('):s.index('[McpForUnityTool(')]
    assert '["permission_changed"] = false' not in error
    assert 'JValue.CreateNull()' in error, 'unknown mutation must remain unknown'

def test_readonly_package_preserved():
    import subprocess
    for rel in subprocess.check_output(['git','ls-tree','-r','--name-only','v0.1.1'],cwd=ROOT,text=True).splitlines():
        if rel.startswith('Editor/') or rel in ('package.json','LICENSE','THIRD_PARTY_NOTICES.md'):
            before = subprocess.check_output(['git','show','v0.1.1:'+rel],cwd=ROOT)
            assert (ROOT/rel).read_bytes() == before, rel

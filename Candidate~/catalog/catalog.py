"""Offline catalog data, not a Unity reader, permission grant or dispatcher."""
import ast
import hashlib
import json
from pathlib import Path


def source_anchor(root, path, start=1, end=None):
    path = Path(path)
    raw = path.read_bytes()
    return {'path': path.relative_to(root).as_posix(), 'start_line': start,
            'end_line': end or len(raw.splitlines()), 'sha256': hashlib.sha256(raw).hexdigest()}


def discover_python_tools(root):
    """Parse actual decorators without importing providers or starting a server.

    Actions are *Python declared* literals, not claims of C# implementation/safety.
    Open string actions stay unknown unless a separate audited record names them.
    """
    root = Path(root)
    tools = []
    for path in sorted((root / 'Server/src/services/tools').rglob('*.py')):
        tree = ast.parse(path.read_text())
        constants = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                try:
                    constants[node.targets[0].id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = [d for d in node.decorator_list if isinstance(d, ast.Call)
                          and isinstance(d.func, ast.Name) and d.func.id == 'mcp_for_unity_tool']
            for decorator in decorators:
                kwargs = {k.arg: ast.literal_eval(k.value) for k in decorator.keywords
                          if k.arg in ('name', 'group', 'unity_target')}
                name = kwargs.get('name', node.name)
                if decorator.args:
                    name = ast.literal_eval(decorator.args[0])
                target = kwargs.get('unity_target', 'self')
                actions = []
                arg = next((a for a in node.args.args if a.arg == 'action'), None)
                if arg is not None and arg.annotation is not None:
                    for item in ast.walk(arg.annotation):
                        if isinstance(item, ast.Subscript) and isinstance(item.value, ast.Name) and item.value.id == 'Literal':
                            literal = ast.literal_eval(item.slice)
                            actions.extend(literal if isinstance(literal, tuple) else [literal])
                # Explicit native action constants used by open-string wrappers.
                if not actions and arg is not None:
                    for key, value in constants.items():
                        if key.endswith('_ACTIONS') and isinstance(value, list) and all(isinstance(v, str) for v in value):
                            actions.extend(value)
                tools.append({'name': name, 'unity_target': name if target == 'self' else target,
                              'group': kwargs.get('group', 'core'),
                              'declared_actions': list(dict.fromkeys(actions)),
                              'has_action_parameter': arg is not None,
                              'parameters': [{'name': a.arg, 'annotation': ast.unparse(a.annotation) if a.annotation else None}
                                             for a in node.args.args if a.arg != 'ctx'],
                              'source': source_anchor(root, path, min(d.lineno for d in node.decorator_list), node.end_lineno)})
    return sorted(tools, key=lambda t: t['name'])


# Descriptions only. This table is not imported by any permission gate.
NAMES_ZH = {
    'apply_text_edits': '文本定点修改', 'batch_execute': '批量执行',
    'create_script': '创建脚本', 'debug_request_context': '请求上下文调试',
    'delete_script': '删除脚本', 'execute_code': '任意代码执行',
    'execute_custom_tool': '自定义工具执行', 'execute_menu_item': '编辑器菜单执行',
    'find_gameobjects': '查找场景对象', 'find_in_file': '文件内容查找',
    'generate_audio': '外部音频生成', 'generate_image': '外部图像生成',
    'generate_model': '外部模型生成', 'get_sha': '脚本内容哈希',
    'get_test_job': '测试任务查询', 'import_model': '外部模型检索与导入',
    'import_model_file': '模型文件导入', 'manage_animation': '动画与控制器',
    'manage_asset': '资产管理', 'manage_build': '构建管理',
    'manage_camera': '相机管理与截图', 'manage_components': '组件修改',
    'manage_editor': '编辑器状态与操作', 'manage_gameobject': '场景对象修改',
    'manage_graphics': '图形渲染与烘焙', 'manage_material': '材质读取与修改',
    'manage_packages': '包与注册表管理', 'manage_physics': '物理系统',
    'manage_prefabs': '预制体管理', 'manage_probuilder': '几何建模',
    'manage_profiler': '性能分析与内存快照', 'manage_scene': '场景管理',
    'manage_script': '脚本读写', 'manage_script_capabilities': '脚本能力查询',
    'manage_scriptable_object': '序列化数据资产修改', 'manage_shader': '着色器读写',
    'manage_texture': '纹理与导入设置', 'manage_tools': '工具组启停',
    'manage_ui': '用户界面管理', 'manage_vfx': '粒子与特效管理',
    'read_console': '控制台读取与清除', 'refresh_unity': '资源刷新与编译',
    'run_tests': '运行编辑器测试', 'script_apply_edits': '脚本结构化修改',
    'set_active_instance': '切换Unity实例', 'unity_docs': 'Unity文档查询',
    'unity_reflect': '类型与成员反射查询', 'validate_script': '脚本校验',
}


def build_candidate_inventory(root):
    """Describe all declared upstream tools without expanding runtime exposure."""
    reads = {'manage_animation': ['controller_get_info','clip_get_info','animator_get_info','animator_get_parameter'], 'manage_material': ['get_material_info'],
             'read_console':['get'], 'manage_scene':['get_active','get_build_settings','get_loaded_scenes','get_hierarchy','validate'],
             'find_gameobjects':['find'], 'manage_packages':['get_package_info'],
             'manage_script':['read'], 'get_sha':['get_sha'], 'manage_shader':['read'], 'unity_reflect':['get_type','get_member','search']}
    tools = []
    for row in discover_python_tools(root):
        actions = reads.get(row['name'], [])
        tools.append({**row, 'name_zh': NAMES_ZH.get(row['name'], '未分类原生能力'),
            'default_decision': 'deny', 'enabled_by_catalog': False,
            'implemented_candidate_read_actions': actions,
            'audit_note_zh': '仅Python声明清单；不证明C#行为安全或授予权限。候选实机可信绑定未完成。'})
    preserved_audit_notes={'find_gameobjects': '仅Python声明清单；不证明C#行为安全或授予权限。候选仅开放by_name/by_tag/by_layer/by_path/by_id；by_component可能触发原生程序集解析回调，保持禁用。候选实机可信绑定未完成。', 'get_sha': '仅规范Assets精确文件的受限原生读取；默认拒绝，仍需本地能力和任务批准。文本/SHA采用原生解码语义，非任意文件/写入/导入/编译权限；实机与Windows文件系统边界仍待验。get_sha工具映射清单manage_script/get_sha，不自动授予正文。', 'manage_script': '仅规范Assets精确文件的受限原生读取；默认拒绝，仍需本地能力和任务批准。文本/SHA采用原生解码语义，非任意文件/写入/导入/编译权限；实机与Windows文件系统边界仍待验。', 'manage_shader': '仅规范Assets精确文件的受限原生读取；默认拒绝，仍需本地能力和任务批准。文本/SHA采用原生解码语义，非任意文件/写入/导入/编译权限；实机与Windows文件系统边界仍待验。'}
    for row in tools:
        if row['name'] in preserved_audit_notes:
            row['audit_note_zh']=preserved_audit_notes[row['name']]
        if row['name'] in ('manage_asset','manage_prefabs'):
            actions=['search','get_info'] if row['name']=='manage_asset' else ['get_info','get_hierarchy']
            row.update(implemented_candidate_effect_actions=actions,audit_note_zh='本地明确认可工程插件是信任前提，不是插件沙箱；不保证阻止内部未知回调。默认关闭，独立效果开关和精确本地任务批准；撤销不强停回调、不回退已发生作用。')
        if row['name']=='get_test_job':
            row.update({'implemented_candidate_effect_actions': ['observe'], 'required_effect': {'kind': 'project_test_job_maintenance', 'version': 1}, 'audit_note_zh': '工程级测试作业状态维护，非纯读取：可恢复/改变其他过期作业、写SessionState和裁剪历史；结果只返回指定TestJobs/job_id。默认关闭，独立副作用开关与本地清单批准；不启动/清空测试、不等待或抢焦点，停止不回退。'})
        if row['name']=='unity_reflect':
            row['audit_note_zh']='受限核心类型元数据：复用固定原生get_type/get_member/search主体，候选独立附加类型仅查unity-engine-core-v1固定13类型，禁止全局程序集解析与扩展方法发现。默认关闭，ApiMetadata独立批准；返回candidate_scope明确不是全工程API。通用上游反射、用户脚本类型、方法/getter执行均未开放；.NET对照测试不替代Unity实机验收。'
        if row['name']=='manage_packages':
            row['audit_note_zh']='仅get_package_info+规范小写已安装包名；ProjectMetadata独立操作批准，披露作者/描述/来源/绝对路径/依赖。只读已注册信息，不触发UPM网络/任务，不授权包内容。原生先取全部注册信息再精确匹配；依赖超1024/输出预算拒绝，非包清单分页。'
    facades = [{'name': 'get_gameobject', 'name_zh': '场景对象摘要', 'unity_target': 'get_gameobject', 'group': 'core', 'declared_actions': [], 'has_action_parameter': False, 'default_decision': 'deny', 'enabled_by_catalog': False, 'implemented_candidate_read_actions': ['read'], 'upstream_uri': 'mcpforunity://scene/gameobject/{instance_id}', 'provenance_kind': 'native_resource_tool_facade', 'audit_note_zh': '复用固定原生资源，候选以工具入口复用任务/撤权链；不是上游原生工具。当前场景/Prefab Stage限定，组件属性只允许显式false；read仅为候选清单权限名。'}, {'name': 'get_gameobject_components', 'name_zh': '组件类型与ID分页', 'unity_target': 'get_gameobject_components', 'group': 'core', 'declared_actions': [], 'has_action_parameter': False, 'default_decision': 'deny', 'enabled_by_catalog': False, 'implemented_candidate_read_actions': ['read'], 'upstream_uri': 'mcpforunity://scene/gameobject/{instance_id}/components', 'provenance_kind': 'native_resource_tool_facade', 'audit_note_zh': '复用固定原生资源，候选以工具入口复用任务/撤权链；不是上游原生工具。当前场景/Prefab Stage限定，组件属性只允许显式false；read仅为候选清单权限名。'}]
    for name, chinese, filename, uri in [('get_project_info','工程信息（含绝对路径）','project_info.py','info'),
            ('get_tags','工程标签列表','tags.py','tags'),('get_layers','工程层名称','layers.py','layers')]:
        facades.append({**facades[0], 'name':name, 'name_zh':chinese, 'unity_target':name,
            'upstream_uri':'mcpforunity://project/'+uri,
            'audit_note_zh':'仅空参数，独立ProjectMetadata任务批准；读取实时工程元数据，不授权资产正文。info原生Python模型只保留工程路径/名称、Unity版本、平台、Assets路径，不代表完整包清单。'})
    for name, chinese, filename, uri in [('get_selection','编辑器选择摘要','selection.py','selection'),
            ('get_windows','编辑器窗口信息','windows.py','windows'),('get_active_tool','当前编辑工具','active_tool.py','active-tool'),('get_prefab_stage','已打开Prefab阶段','prefab_stage.py','prefab-stage')]:
        facades.append({**facades[0], 'name':name, 'name_zh':chinese, 'unity_target':name,
            'upstream_uri':'mcpforunity://editor/'+uri,
            'audit_note_zh':'仅空参数，独立EditorMetadata批准。披露全编辑器选择/窗口标题坐标/当前工具/当前Prefab Stage路径；不是资产正文权限，不选择/聚焦/打开Prefab。选择和窗口原生无分页、输出超预算拒绝；窗口读取异常可能跳过。'})
    facades.append({**facades[0], 'name':'get_menu_items','name_zh':'菜单名称列表','unity_target':'get_menu_items',
        'upstream_uri':'mcpforunity://menu-items','audit_note_zh':'仅空参数，独立EditorMetadata/get_menu_items/read批准；原生refresh=true只重建TypeCache菜单元数据缓存，不刷新资产/执行菜单。原生扫描异常会保留旧缓存/空列表，不承诺穷尽；无分页，输出超4096项/预算拒绝。'})
    facades.append({**facades[0],'name':'get_tests','name_zh':'非缓存实时测试发现','unity_target':'get_tests','group':'testing',
        'implemented_candidate_read_actions':[],'implemented_candidate_effect_actions':['discover'],
        'upstream_uri':'mcpforunity://tests/{mode}',
        'audit_note_zh':'本地明确认可工程插件是信任前提，不是插件沙箱；不保证阻止内部未知回调。默认关闭，独立效果开关和精确本地任务批准；撤销不强停回调、不回退已发生作用。 候选附加非缓存provider，不调用可能缓存的公开资源；不运行测试、不维护作业、不抢焦点。'})
    resource_files={'get_tests':'tests.py','get_menu_items' :'menu_items.py','get_selection':'selection.py','get_windows':'windows.py','get_active_tool':'active_tool.py','get_prefab_stage':'prefab_stage.py','get_project_info':'project_info.py','get_tags':'tags.py','get_layers':'layers.py'}
    for row in facades:
        row['source'] = source_anchor(Path(root), Path(root)/'Server/src/services/resources'/resource_files.get(row['name'],'gameobject.py'))
    return {'schema_version': 1, 'product_ready': False, 'permission_grant': False,
            'count': len(tools), 'tools': tools, 'resource_facades': facades,
            'scope_zh': '离线原生能力目录；材质候选写另走专用受限入口，不开放原生泛用写工具。'}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='从固定源码生成只描述、不授权的中文目录')
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build_candidate_inventory(args.upstream)
    # Refuse to overwrite evidence. Never import/execute upstream tools.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


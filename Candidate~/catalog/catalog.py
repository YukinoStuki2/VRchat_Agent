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
    reads = {'manage_animation': 'controller_get_info', 'manage_material': 'get_material_info'}
    tools = []
    for row in discover_python_tools(root):
        action = reads.get(row['name'])
        tools.append({**row, 'name_zh': NAMES_ZH.get(row['name'], '未分类原生能力'),
            'default_decision': 'deny', 'enabled_by_catalog': False,
            'implemented_candidate_read_actions': [action] if action in row['declared_actions'] else [],
            'audit_note_zh': '仅Python声明清单；不证明C#行为安全或授予权限。候选实机可信绑定未完成。'})
    return {'schema_version': 1, 'product_ready': False, 'permission_grant': False,
            'count': len(tools), 'tools': tools,
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


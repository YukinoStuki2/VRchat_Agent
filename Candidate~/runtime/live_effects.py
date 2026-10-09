"""Thin policy/wire facade to shipped readers, not a second Unity implementation.
No upstream mixed-action wrappers: those refresh/cache or expose write branches.
"""
import json
import re
import unicodedata
from fastmcp import Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from transport.plugin_hub import PluginHub

TOOLS={'manage_asset','manage_prefabs','get_tests'}
ACTIONS={'manage_asset':{'search','get_info'},'manage_prefabs':{'get_info','get_hierarchy'},'get_tests':{'discover'}}

def asset_path(value):
    if (type(value) is not str or not value.startswith('Assets/') or len(value.encode('utf-16-le'))//2>490
            or any(unicodedata.category(c)=='Cc' or c in '\\:%<>"|?*' for c in value)
            or any(not p or p in ('.','..') or p!=p.strip() or p.endswith('.') or
                   re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',p.split('.')[0]) for p in value.split('/'))):
        raise ToolError('invalid_asset_path')
    return value

def params(name,args):
    if name=='get_tests':
        if set(args)!={'mode'} or args['mode'] not in ('EditMode','PlayMode'):raise ToolError('invalid_discovery_mode')
        return 'discover','TestDiscovery/'+args['mode'],dict(args)
    action=args.get('action')
    if type(action) is not str or action not in ACTIONS[name]:raise ToolError('operation_not_enabled')
    if name=='manage_prefabs':
        if set(args)!={'action','prefab_path'}:raise ToolError('invalid_prefab_arguments')
        path=asset_path(args['prefab_path'])
        if not path.endswith('.prefab'):raise ToolError('invalid_prefab_path')
        return action,'PrefabReads/'+path,{'action':action,'prefabPath':path}
    keys={'action','path','generate_preview'}
    if not keys<=args.keys() or args['generate_preview'] is not False:raise ToolError('asset_preview_forbidden')
    path=asset_path(args['path'])
    if action=='get_info':
        if set(args)!=keys:raise ToolError('invalid_asset_arguments')
    else:
        keys|={'page_number','page_size'}
        if (not keys<=args.keys() or set(args)-keys-{'search_pattern','filter_type','filter_date_after'}
                or type(args['page_number']) is not int or not 1<=args['page_number']<=1000000
                or type(args['page_size']) is not int or not 1<=args['page_size']<=50):raise ToolError('invalid_asset_page')
        for k in ('search_pattern','filter_type','filter_date_after'):
            if k in args and (type(args[k]) is not str or len(args[k].encode('utf-16-le'))//2>128 or any(unicodedata.category(c)=='Cc' for c in args[k])):
                raise ToolError('invalid_asset_filter')
        # Date parsing uses the final Unity invariant parser, without broadening input here.
    mapping={'generate_preview':'generatePreview','page_number':'pageNumber','page_size':'pageSize','search_pattern':'searchPattern','filter_type':'filterType','filter_date_after':'filterDateAfter'}
    return action,'AssetReads/'+path,{mapping.get(k,k):v for k,v in args.items()}

def effect_kinds(name,action):
    if name=='get_tests':return ['test_discovery_callbacks']
    return ['asset_load_callbacks','prefab_contents_callbacks'] if name=='manage_prefabs' and action=='get_hierarchy' else ['asset_load_callbacks']

def manifest(pairs,targets,effects):
    if len(pairs)!=1 or len(targets)!=1:raise ToolError('effect_requires_separate_exact_plan')
    name,action=pairs[0];target=targets[0]
    prefix='TestDiscovery/' if name=='get_tests' else 'PrefabReads/' if name=='manage_prefabs' else 'AssetReads/'
    if type(target) is not str or not target.startswith(prefix):raise ToolError('invalid_effect_target')
    path=target[len(prefix):]
    if name=='get_tests':
        if path not in ('EditMode','PlayMode'):raise ToolError('invalid_discovery_mode')
    else:
        asset_path(path)
        if name=='manage_prefabs' and not path.endswith('.prefab'):raise ToolError('invalid_prefab_path')
    wanted=[{'kind':k,'version':1} for k in effect_kinds(name,action)]
    if (type(effects) is not list or effects!=wanted or any(type(e) is not dict or type(e.get('version')) is not int for e in effects)):
        raise ToolError('explicit_effects_required')

def receipt(name,args,result):
    if type(result) is not dict or type(result.get('success')) is not bool:raise ValueError('invalid_response')
    if result['success'] is not True:return
    data=result.get('data');r=data.get('candidate_effects') if type(data) is dict else None
    kind=effect_kinds(name,args.get('action','discover'))[-1]
    fields={'kind','version','read_only','all_mutations_observed','callback_effects_path_bounded'}
    fields|=({'observed_at_utc','pagination_consistency'} if name=='manage_asset' else {'cleanup_confirmed'})
    if name=='manage_prefabs':fields|={'load_started','unload_started'}
    if (type(r) is not dict or set(r)!=fields or r['kind']!=kind or type(r['version']) is not int or r['version']!=1
            or any(r[k] is not False for k in ('read_only','all_mutations_observed','callback_effects_path_bounded'))):raise ValueError('invalid_receipt')
    if name=='manage_asset':
        if type(r['observed_at_utc']) is not str or not 1<=len(r['observed_at_utc'])<=64 or r['pagination_consistency']!='live_not_snapshot':raise ValueError('invalid_receipt')
    else:
        if r['cleanup_confirmed'] is not True:raise ValueError('cleanup_unconfirmed')
        if name=='manage_prefabs' and any(r[k] is not (args['action']=='get_hierarchy') for k in ('load_started','unload_started')):raise ValueError('invalid_receipt')
    if len(json.dumps(result,ensure_ascii=False).encode())>262144:raise ValueError('response_budget')

def register(server,runtime):
    annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=True,idempotentHint=False,openWorldHint=True)
    async def send(name):
        args=runtime.current().arguments
        wire=params(name,args)[2]
        try:
            result=await PluginHub.send_command(await runtime.connection(),name,wire)
            receipt(name,args,result)
            return result
        except Exception:
            raise ToolError('live_effect_unconfirmed; effects_may_have_occurred=true; 副作用读取未确认，不自动重试或回退。') from None
    @server.tool(name='manage_asset',annotations=annotations)
    async def read_asset(action:str,path:str,generate_preview:bool,ctx:Context,page_number:int|None=None,page_size:int|None=None,search_pattern:str|None=None,filter_type:str|None=None,filter_date_after:str|None=None)->dict:
        """实时资产search/get_info；独立AssetReads/Assets/...任务，effects=[{kind:asset_load_callbacks,version:1}]。
        必须本地认可工程插件、开启资产效果权限并批准任务；不是插件沙箱。generate_preview必须显式false。
        search须显式page_number>=1、page_size=1..50；上限4096匹配，不是快照。禁止刷新、预览和写分支。
        """
        return await send('manage_asset')
    @server.tool(name='manage_prefabs',annotations=annotations)
    async def read_prefab(action:str,prefab_path:str,ctx:Context)->dict:
        """实时Prefab get_info/get_hierarchy；精确PrefabReads/Assets/*.prefab与本地插件信任、效果权限、任务批准。
        get_info要求asset_load_callbacks；get_hierarchy依次要求asset_load_callbacks和prefab_contents_callbacks，version均1。
        不保存、不打开Stage；可能执行插件回调，不是沙箱。仅清理自有临时实例，清理未知阻断后续；至多1000节点/64层。
        """
        return await send('manage_prefabs')
    @server.tool(name='get_tests',annotations=annotations)
    async def discover_tests(mode:str,ctx:Context)->dict:
        """非缓存实时发现，mode精确EditMode或PlayMode；独立TestDiscovery/<mode>、get_tests/discover任务。
        effects=[{kind:test_discovery_callbacks,version:1}]；本地认可插件+独立效果开关+本地任务批准，非插件沙箱。
        不运行测试、不维护作业、不抢焦点。预算4096节点/64层/30秒观测期限；不强停阻塞回调，撤权后清理自有枚举器/订阅。
        """
        return await send('get_tests')

"""Cloud熱更新後核對製片模組介面；只在版本不相容時重載。"""
import importlib
import inspect
import logging
import threading

LOGGER = logging.getLogger('interior_studio.runtime')
_LOAD_LOCK = globals().get('_LOAD_LOCK',threading.RLock())
BGM_API_VERSION = 3


def _compatible(module, function, music_arguments=False):
    if getattr(module, 'BGM_API_VERSION', None) != BGM_API_VERSION:
        return False
    try:
        parameters = inspect.signature(getattr(module, function)).parameters
    except (AttributeError, TypeError, ValueError):
        return False
    return not music_arguments or all(name in parameters and parameters[name].kind != inspect.Parameter.POSITIONAL_ONLY
                                      for name in ('music', 'music_asset'))


def video_modules():
    """不清除Session State；避免新app.py呼叫記憶體中的舊payload／export。"""
    with _LOAD_LOCK:
        # 共用標題與音樂先載入，消費端再重新匯入新函式，避免Cloud混用舊介面。
        specs = [('studio.cover', 'new_cover', False), ('studio.body', 'effective_title', False),
                 ('studio.music', 'load_music', False), ('studio.component', 'payload', True),
                 ('studio.export', 'export_video', True), ('studio.sync', 'consume_editor_event', False)]
        modules = [importlib.import_module(name) for name, _, _ in specs]
        mismatches = [name for module, (name, function, music_args) in zip(modules, specs)
                      if not _compatible(module, function, music_args)]
        if mismatches:
            LOGGER.warning('APP_RUNTIME_RELOAD incompatible_modules=%s expected_bgm_api=%s', ','.join(mismatches), BGM_API_VERSION)
            importlib.invalidate_caches()
            # 相關模組一起更新，避免修好編輯器後輸出仍使用舊BGM介面。
            modules = [importlib.reload(module) for module in modules]
        if any(not _compatible(module, function, music_args)
               for module, (_, function, music_args) in zip(modules, specs)):
            LOGGER.error('APP_RUNTIME_RELOAD deployment_files_incompatible expected_bgm_api=%s', BGM_API_VERSION)
            raise RuntimeError('部署檔案版本不一致，請等候GitHub更新完成後，在Manage app選Reboot app重新載入。')
        return tuple(modules[-3:])

"""schemas 包 · 请求/响应数据契约（对齐《详细设计》§2.21 + §4.2）。

信封(Envelope)与错误码(ErrorCode)为全站统一契约，接口 100% 命中(§11 DoD)。
"""

__all__: list[str] = ["envelope", "errors"]

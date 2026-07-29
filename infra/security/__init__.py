"""infra.security 包 · 鉴权与加密(§2.19.6 单用户 MVP 轻量鉴权)。

- AES-256-GCM 密码可逆加密(密钥经 env 注入，等价密钥外部托管，§2.19.6)。
- AES 会话令牌(前后端 AES 加解密，无 JWT 依赖；§2.19.6 未指定 JWT)。

> 评审接受：单用户 + 内网/本机部署下，AES 可逆加密密码方案风险已接受(S3)。
"""

from infra.security import crypto, token

__all__: list[str] = ["crypto", "token"]

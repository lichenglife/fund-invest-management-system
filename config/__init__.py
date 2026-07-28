"""config · 配置加载(开发规范§9.1 Twelve-Factor / §1.7)。

环境分离(dev/test/staging/prod)，密钥走环境变量/Docker Secrets，禁止硬编码(§9.1)。
"""

__all__: list[str] = ["settings"]

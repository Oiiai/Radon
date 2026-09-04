# Radon

此仓库包含 Radon（氡，`.rdn`）格式的解析器。

仓库同时包含 VS Code 语言扩展，安装扩展后即可自动识别 `.rdn` 文件并提供语法高亮。
在 VS Code 中打开本目录，按 `F5` 启动扩展开发主机进行预览。

```python
import rdn

with open("settings.rdn", "r", encoding="utf-8") as file:
    config = rdn.load(file)

value = config["_114514abc"]["key"]
```

也可以直接传入文件路径：`config = rdn.load("settings.rdn")`。

解析器支持：

- 类似 `[_114514abc]` 的节
- 带引号的键和字符串值
- 整数、浮点数、`true`/`false` 值以及可嵌套列表（使用 `()`）
- 从第 0 列的 `;` 开始的注释

`parse(text)` 返回 `dict[str, dict[str, obrdnt]]`。语法无效、节重复或键重复时，
会抛出带有源文件行号的 `rdnParseError`。

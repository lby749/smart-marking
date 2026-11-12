# Smart marking

供支持技能文件的 AI Agent 按教师提供或确认的标准，结合已授权的浏览器页面进行视觉阅卷、成绩核验和答题反馈。将整个 `smart-marking` 文件夹安装到 Agent 的技能目录，重新加载技能后调用 `smart-marking`。不同客户端的安装目录与技能发现方式以客户端说明为准。

## 包含内容

- `SKILL.md`：通用阅卷流程、教师评分口径、人工复核和安全提交要求。
- `references/cdp-implementation.md`：CDP 接入、原图读取及回填核验步骤。
- `references/zhixue.md`：智学网页面实测经验和异常恢复注意事项。
- `scripts/cdp_bridge.py`：面向已有授权调试会话的本地桥接程序；无模型调用，不自动评分或提交。
- `tests/test_cdp_bridge.py`：独立模拟浏览器及页面的基础连接和取图测试。

## 环境与使用

需要 Python 3、`playwright` 和 `Pillow`；执行 `python -m pip install -r requirements.txt`。浏览器必须已经由用户登录，并通过其允许的方式开放调试接入；脚本不会开启调试、处理验证码或绕过浏览器权限。详细协议见 `references/cdp-implementation.md`。

评卷模型、视觉识别、教师标准理解、页面定位、分数判断和提交验证由宿主 Agent 负责；脚本的 `eval` 可执行页面 JavaScript，使用者必须控制调用及授权。不同平台的页面结构不同，不能声称开箱即支持全部平台和题型；实际使用前需先做有代表性的试运行并让教师核对。

可选测试：安装 Microsoft Edge 后，在技能目录运行 `python -m unittest discover -s tests -v`。测试启动独立的无头浏览器和本地模拟页面，不连接用户实际浏览器。也可通过 `TEST_BROWSER_CHANNEL` 指定 Playwright 已安装的其他 Chromium 浏览器通道。

## 隐私与许可

不要把答卷图片、浏览器配置、Cookie、签名链接、学生身份信息、日志或成绩放进公开仓库。程序本身不上传图片，也不调用第三方模型 API；使用外部 Agent、模型或服务时，数据处理由对应产品和使用者负责。

本项目采用 [MIT 许可证](LICENSE)。

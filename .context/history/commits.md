# Commit History

## 2026-04-23

### feat(ac-api): 添加 SKSPIOT 智慧园区 OpenAPI 导出 skill
- **ID**: 787e04d2-16fa-4b25-a969-9fe6a17f283e
- **分支**: main
- **决策**:
  - 新增 ac-api skill 用于从 Java Service 接口导出 OpenAPI 3.1 JSON
  - 包含完整的测试套件和打包分发文件
  - 同时更新 ac-commit 的 .context 前置判断逻辑
- **变更文件**:
  - dist/ac-api.skill
  - hooks/tool-tips-post.sh
  - skills/ac-api/SKILL.md
  - skills/ac-api/scripts/export_openapi_from_java.py
  - skills/ac-api/scripts/generate_openapi.py
  - skills/ac-api/tests/fixtures/tmp_photovoltaic_business_center.java
  - skills/ac-api/tests/test_export_openapi_from_java.py
  - skills/ac-commit/SKILL.md
- **测试**: skills/ac-api/tests/test_export_openapi_from_java.py

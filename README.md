# laoluskills

我的 Hermes Agent skills 集合。每个 skill 是一个独立子目录,自带 SKILL.md / scripts/ / references/。

## Skills 索引

| Skill | 用途 | 状态 |
|---|---|---|
| [chinese-ecommerce-data-harvesting](./chinese-ecommerce-data-harvesting/) | 中文电商数据抓取(闲鱼/小红书/淘宝/京东/头条),含 6 维度选品调研模板 | ✅ active |

## 添加新 skill

每个 skill 是独立子目录,目录名用 kebab-case(全小写 + 短横线)。`SKILL.md` 是入口,带 YAML frontmatter 描述,触发时由 Hermes 自动加载。

## 备份策略

- 每次重要更新(选择器/逻辑/新功能)一个 commit
- commit message 格式: `<skill>: <改动摘要>` (e.g. `xianyu-detail: v12 加 images 字段`)
- 自动屏蔽: cookie 文件、HTML 快照、临时日志、数据库二进制

## Owner

dark@home — 个人用,不公开。仓库 Private,只 owner 可见。

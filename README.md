# 🐾 Dingchun AI Assistant (AI Questions Bank) V1.0

> **一个基于本地大模型（LM Studio）的多 Agent 智能题库与知识库管理系统。**
> *Designed by a Product Manager, Powered by Python & LLMs.*

## 📖 项目简介

**Dingchun AI Assistant** (Repo Name: `AI_Questions_Bank`) 是一个专为教育、培训及出版行业设计的智能化题库管理工具。作为一个由产品经理设计并开发的“人机协作”系统，它不仅仅是一个简单的 RAG 应用，更是一个包含数据清洗（ETL）、知识库构建、多 Agent 协同出题以及人工审核（Human-in-the-loop）的完整业务闭环工具。

本项目核心旨在解决传统题库建设中“人工效率低”和“AI 幻觉多”的痛点，通过本地知识库强约束，实现高质量的题目生成与管理。

## ✨ 核心功能

本系统主要由三大模块构成：

### 1. 🧠 智能题库 (Question Bank)
* **多 Agent 协同编题**：采用流水线架构，由出题 Agent（编写题干/正确项）、干扰项 Agent（编写错误项）和 审题 Agent（逻辑校验）协作完成。
* **AI 自动拆解**：支持将非结构化文本拆解为标准试题格式。
* **RAG 辅助审题**：内置“定春”调度器，结合本地检索和线上模型（Kimi/Qwen）对题目进行事实性校验。

### 2. 📚 知识库工厂 (Knowledge Base)
* **本地化书本管理**：支持读取本地路径书籍，保护版权与隐私。
* **智能切分与 ETL**：
    * **Step 1 Split**: 按段落物理切分。
    * **Step 2 Process (AI)**: 调用本地模型将碎片段落转写为语义完整的知识片段（核心亮点）。
    * **Step 3 Embed**: 向量化存入 Chroma 数据库。
* **人工审核流程**：提供审核界面，确保入库知识的绝对准确性。

### 3. 🛠️ 效率工具 (Toolkit)
* **向量检索实验室**：支持基于元数据（Metadata）的高级过滤检索。
* **AI 一致性对比**：自动对比生成的文本与教材原文的一致性。
* **配置中心**：可视化管理检索集合与模型参数。

## 🏗️ 系统架构

本项目采用 **前后端分离** 架构，后端基于 Python，前端采用原生 HTML/JS 模块化开发，数据层使用 MySQL + Vector DB。

```text
Project Root
├── main.py                     # 程序入口，Web服务启动
├── config.py                   # 全局配置 (Key, Path, Model)
├── backend/                    # 后端核心业务
│   ├── books/                  # 书籍 ETL 流水线 (Split -> Process -> Embed)
│   ├── dingchun/               # 核心调度器 (Review Agent & RAG Tools)
│   ├── knowledge/              # 知识库 CRUD 与 审核逻辑
│   ├── question_agent/         # 编题 Agent 集群 (出题/干扰项/审题)
│   ├── search/                 # 检索与元数据过滤算法
│   ├── routers/                # API 路由层
│   └── tools/                  # 底层工具箱 (SQL, AI Call, Context)
├── frontend/                   # 前端界面 (Pages, JS, CSS)
├── dbtools/                    # 数据库维护脚本 (本地运维用)
└── Z_DOC/                      # 开发文档与 SQL 结构


⚙️ 环境依赖与配置 (必读)
1. 硬件与模型环境
推荐环境：Windows / Linux

模型后端：本项目深度依赖 LM Studio 提供本地模型 API 服务。

原因：针对 AMD 显卡或非 CUDA 环境，LM Studio 提供了最稳定的跨平台兼容性。

2. 并发说明
⚠️ 注意：本项目目前定位为单人使用的桌面级工具。

未做高并发处理。

本地显卡资源有限，建议线性操作（等待一个任务完成后再进行下一个），以免导致模型重载或显存溢出（OOM）。

🚀 快速开始
第一步：克隆项目与安装依赖
Bash

git clone [https://github.com/xiaoxi324/AI_Questions_Bank.git](https://github.com/xiaoxi324/AI_Questions_Bank.git)
cd AI_Questions_Bank
pip install -r requirements.txt

第二步：数据库准备
安装 MySQL 8.0+。

查看 Z_DOC/doc_sql.txt 初始化表结构。

确保向量数据库依赖库已安装。

第三步：配置 Config (关键)

修改配置：

填入 API Keys (如需使用云端能力)。

确认 LM Studio 的本地监听端口（默认 6324 或 1234）。

路径配置已使用相对路径优化，通常无需修改即可运行。

第四步：启动
启动 LM Studio 并加载模型（开启 Server 模式）。

运行主程序：

Bash

python main.py
浏览器访问控制台输出的本地地址（通常为 http://localhost:port）。

🗺️ 规划路线图 (Roadmap)
[x] V1.0: 完成题库管理、基础 RAG、多 Agent 编题、执业药师领域适配。

[ ] V1.5: 引入 知识图谱 (Knowledge Graph)，通过实体关系固化知识沉淀。

[ ] V2.0: 学员端开发，支持基于个人知识库的自适应学习、刷题与模拟考。

🤝 贡献与反馈
本项目由独立开发者维护。 欢迎提交 Issue 或 Pull Request。

📄 License
本项目采用 GPL-3.0 协议开源。

Created with ❤️ by Dingchun Team.

📞 联系与交流
如果你对本项目感兴趣，或者有AI项目的合作需求，欢迎联系我：
微信号：yuuko324
加好友请注明 GitHub 

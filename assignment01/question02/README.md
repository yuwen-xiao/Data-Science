# Assignment 01 · Question 02

数据预处理方法：**主成分分析（PCA）**。

本版本保留第一版主体内容，在格式修复的基础上重排了求解逻辑，并删除原来的“资料如何组织”页、新增“参考文献与鸣谢”页。最终为 18 页。

## 交付内容

- `slide.md`：18 页 `jyyslide-md` 演示稿源文件
- `dist/index.html`：生成后的 Web 幻灯片
- `dist/assignment01-question02-pca.pdf`：18 页 PDF 版本
- `assets/`：PCA 讲解图
- `data/`：UCI Wine 原始数据及字段说明
- `scripts/generate_figures.py`：图和统计结果的复现脚本
- `scripts/fetch_pca_sources.py`：公开资料抓取与摘录脚本
- `scripts/export_pdf.py`：PDF 导出脚本
- `sources/`：参考资料和抓取日志
- `pca_metrics.json`：数值结果、载荷和代表性样本

## 内容结构

1. 为什么需要降维
2. PCA 的几何直觉
3. 最大方差目标
4. 协方差矩阵与特征值推导
5. SVD 如何实现 PCA
6. 如何选择主成分数量
7. 完整 PCA 流程
8. Wine 案例：13 维降低到 3 维
9. 主成分解释与方差损失
10. 应用、边界和结论
11. 参考文献与鸣谢

## 数据与结果

- 数据集：UCI Wine Recognition
- 样本数：178
- 原始特征数：13
- 预处理：按特征做 Z-score 标准化
- 前三个主成分解释方差：36.20% + 19.21% + 11.12%
- 三维累计解释方差：66.53%
- 三维未保留方差：33.47%

## 复现

仓库中已经包含生成后的 Web 幻灯片和 PDF。重新生成图表时：

```bash
cd assignment01/question02
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_pca_sources.py
.venv/bin/python scripts/generate_figures.py
```

幻灯片使用 `jyyslide-md` 主题生成。将本目录 `slide.md` 作为输入运行主题转换器后，会在 `dist/` 下生成网页；随后可执行：

```bash
python scripts/export_pdf.py
```

打开 `dist/index.html` 浏览。方向键或 `hjkl` 翻页，`Esc` 查看总览。

## 主要文件

- [PDF 演示稿](dist/assignment01-question02-pca.pdf)
- [Web 幻灯片](dist/index.html)
- [Markdown 源文件](slide.md)
- [PCA 图](assets/)
- [UCI Wine 数据](data/wine.data)
- [资料清单与抓取记录](sources/)

## 本次评审改进

- 修正 Z-score 标准化下的样本变换和重构公式
- 统一使用 `\tilde x_i` 表示预处理后的样本
- 明确区分一维投影得分、三维得分和得分矩阵
- 精简第 11 页长向量，完整数值保留在数据文件中
- 精简第 13 页载荷表，每页只保留主要方向权重
- 第 15 页改为四张应用卡片，第 16 页压缩为五条关键边界
- 第 17 页结论改为单列编号结构，提升投影可读性
- 放大图表内部字号，移除图内重复标题

## 格式修复

- 行内公式统一使用 `$...$`
- 独立公式统一使用 `$$...$$`
- `S^2/(n-1)`、三维坐标和载荷系数均正常渲染
- 修复 Markdown 加粗、列表和表格源码泄露
- 修复长文本和表格的右侧裁切
- 原“资料如何组织”页已删除，新增独立的“参考文献与鸣谢”页
- Wine 数据集名称链接到 UCI 官方数据页
- 算法流程页补充 CSDN 博客参考链接
- 明确 SVD 与 PCA 的对应关系：主成分方向、得分、解释方差和解释方差比例
- 将主成分数量选择移到完整流程之前，避免先使用后解释

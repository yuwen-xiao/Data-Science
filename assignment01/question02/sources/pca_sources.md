# PCA 资料来源与使用说明

## 一、资料组织原则

- **论文与教材**：用于确认 PCA 的定义、推导、性质和历史来源。
- **官方文档**：用于核对算法步骤、中心化/标准化差异和实现方式。
- **博客**：用于学习直观解释、图示顺序和案例组织，不把博客当作唯一依据。

## 二、核心文献

1. Pearson, K. (1901). *On Lines and Planes of Closest Fit to Systems of Points in Space*. Philosophical Magazine, 2(11), 559–572. DOI: [10.1080/14786440109462720](https://doi.org/10.1080/14786440109462720)
2. Hotelling, H. (1933). *Analysis of a Complex of Statistical Variables into Principal Components*. Journal of Educational Psychology, 24, 417–441. DOI: [10.1037/h0071325](https://doi.org/10.1037/h0071325)
3. Jolliffe, I. T. (2002). *Principal Component Analysis* (2nd ed.). Springer. DOI: [10.1007/b98835](https://doi.org/10.1007/b98835)
4. Abdi, H., & Williams, L. J. (2010). *Principal component analysis*. WIREs Computational Statistics, 2(4), 433–459. DOI: [10.1002/wics.101](https://doi.org/10.1002/wics.101)
5. Shlens, J. (2014). *A Tutorial on Principal Component Analysis*. arXiv: [1404.1100](https://arxiv.org/abs/1404.1100)

## 三、官方文档与博客

6. scikit-learn. *PCA — scikit-learn documentation*. [链接](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html)
7. scikit-learn. *2.5. Decomposing signals in components (PCA section)*. [链接](https://scikit-learn.org/stable/modules/decomposition.html#pca)
8. GeeksforGeeks. *Principal Component Analysis (PCA)*. [链接](https://www.geeksforgeeks.org/data-analysis/principal-component-analysis-pca/)
9. CSDN. *什么是主成分分析（PCA）——从零开始讲清楚（超详细版）*. [链接](https://blog.csdn.net/qq_54700138/article/details/146046975)

## 四、数据来源

10. UCI Machine Learning Repository. *Wine Recognition*. [链接](https://archive.ics.uci.edu/dataset/109/wine)

## 五、本次爬取记录

本次使用 [`scripts/fetch_pca_sources.py`](../scripts/fetch_pca_sources.py) 以正常 User-Agent、低频率请求抓取公开页面，保存标题、描述、状态码和文本摘录。抓取结果见 [`crawl_log.json`](crawl_log.json)，原始轻量文本摘录在 [`raw/`](raw/) 下。

> 博客内容仅用于辅助理解。核心公式与实现结论已与 scikit-learn 官方文档和 Shlens 教程交叉核对。

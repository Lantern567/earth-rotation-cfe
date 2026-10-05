# Figure 5 绘图说明

绘图入口：`scripts/figures/plot_strict_revision.py`。在复现包根目录执行：

```text
python scripts/figures/plot_strict_revision.py --figure fig5
```

输出为包内 `figures/Fig5.png` 与 `figures/Fig5.pdf`。本次交付的同一文件也位于论文交付目录 `Figures/`。输入和原投稿模板均保留。

## 输入与边界

- `results/storage/r3_dispatch_grid_2030.csv`：3,744行，SHA256 `961bc51a1e59efe7ab7cd1130c3fac57244ca9cef022ed39286811a7656dc10b`。
- `results/storage/r3_dispatch_yearly_phi1.csv`：3,744行，SHA256 `52fe11cc2b651aea388454603c7d77c924c806324e86e6b19e4093f9936cac64`。
- 合并后6,864个唯一绘图情景键，104个国家；每一情景均含104个国家。所有输入的 solver_status 为0、unmet_mwh 为0、firm_share 为1。
- 成本是跨国覆盖移除后、国内供给重新拟合后的剩余国内负荷供电成本；每个情景按其剩余国内平均负荷100 MW归一化。接收方购电、计算、网络和合同成本不包含在本图中。
- 网络横轴表示 additional-network RTT budget。国家代码 `NA` 作为 Namibia 保留。
- 本次仅重绘已有严格结果，没有重新运行调度模型。

## 四个面板

**a：瀑布图。** 在2030年、Mix、φ=1下，分别计算104个国家各自的 Π=100×(lcoe_elec−lcoe_gen)/lcoe_gen，再取每个网络预算的国家中位数。50 ms为起点柱，后续浮动柱显示相邻预算的变化，虚线连接相邻数值；Π=0为发电成本参照。六个值依次为60.796124%、61.916090%、57.747863%、57.278421%、56.137631%、56.137631%。100→150 ms下降4.168227个百分点，为实际最大下降。

**b：36扇区极坐标玫瑰图。** 六个网络预算各含六个φ值（0、0.2、0.4、0.6、0.8、1）。每个扇区的储能和辅助服务部分分别是100×mean(lcoe_store)/mean(lcoe_gen)与100×mean(lcoe_anc)/mean(lcoe_gen)，三个均值均来自该情景的104个国家；外圈颜色和标签表示网络预算。该面板沿用原投稿的均值成本比聚合定义。

**c：双分面平滑分布与年度轨迹。** 上方国内50 ms和全球500 ms两个分面分别显示2025、2030、2035、2040、2045、2050年的104国Π分布，全部采用Mix与φ=1。平滑分布使用Gaussian KDE，带宽因子0.42；白色竖线标记每年的国家中位数，彩色圆点和虚线连接各年中位数。下方为全部六个网络预算的国家中位数年度轨迹。分布横轴为0–260%，覆盖全部严格数据的最大Π=257.807497%；国内与全球分面的所有实际国家值均在范围内。2025/2030/2050的国内中位数分别为61.177258/60.796124/67.739350%，全球分别为56.409755/56.137631/62.880275%。

**d：三幅Robinson地图。** 显示全球500 ms、Mix、φ=1下2025、2030和2050年的各国Π。国家轮廓、地图投影、配色、年度标签和图例位置沿用原投稿。色标范围30–120%，使用 `extend='both'`，低于或高于范围的真实值分别使用两端颜色及两端扩展箭头表示；灰色为无数据区域。

## 样式、尺寸和核查

- 四面板布局、原紫色与青绿色/橙色编码、DejaVu Sans字体、原图例位置和原地图流程保留。
- 原始与最终Matplotlib画布均为13.2×12.8英寸。
- 原始与最终PNG均为3814×3672像素，300 dpi。
- 原始与最终PDF页面均为915.209106×881.135376 pt。
- 原模板为 `paper_release/figures/fig4_routing_cost`，模板PNG SHA256 `0b2f14d0dca84599c3337d35168f773f44b1ee4f758bd7a4ec579ae9889bde8a`，PDF SHA256 `a1ecf05cc79f24303ec424e235cd57623d9b8645f7dcd9f96de7412f5c84739d`。
- 最终PNG SHA256 `1dfebfa142c1f6e9abe6580cc7f2e7296e1bf095a150fcf21ea23f4d101f29b8`；最终PDF SHA256 `165dc8662cdad28477e6ed9f0b422e9c9bc20ceee26c1a38f4111c868774108e`。
- PNG与PDF实际渲染图均已查看；PDF没有页面外文本块。年度文字显示在分布填色上层。
- Figure S9函数SHA256 `0ca36fa336ef47a45416e0ec5e0a5a482b41a1ca98138a7846927243cc0e5957`，Figure S9 PNG SHA256 `c1bba62b46078b4ff3465b4cacb6779427c15f9c7f98e1dda07ba8f653370622`，均保持不变。

## 中间聚合表与验证

- `fig5_waterfall_strict.csv`：6行，a面板中位数与相邻变化。
- `fig5_rose_strict.csv`：36行，b面板均值成本、国家数量和两部分百分比。
- `fig5_annual_strict.csv`：36行，c面板每年每预算国家数量、中位数、最小值和最大值。
- `fig5_maps_strict.csv`：312行，d面板三个年度的104国成本与Π。
- `fig5_style_validation.json`：源文件SHA256、严格服务检查、聚合定义与绘图范围。
- `fig5_asset_validation.json`：实际原始/最终尺寸、图件SHA256、文本边界检查与S9保持检查。

README

# PrimeLog

**Decompose Anything. Understand Everything.**

PrimeLog 是一个基于**素数唯一分解定理**的通用复合事件日志与可观测性框架。

它能将任意多维复合事件（错误、行为、异常、攻击、营销路径、设备状态……）唯一编码为单个整数，实现极致压缩、精确模式挖掘、跨系统迁移与动态时域分析。

从个人项目到企业级大数据、物联网、商业营销、灰产监测、网络安全……PrimeLog 都能提供前所未有的洞察力。

---

### ✨ 核心优势

- **素数复合编码**  
  任意组合（例如：超时 + 权限错误 + 数据外泄 = 2×3×7=42）都被映射为唯一整数，支持秒级分解与精确还原。

- **张量级智能分析**  
  对数变换后形成稀疏张量，可直接进行分解、聚类、周期检测与模式挖掘。

- **动态时域分析**  
  原生支持真实时间戳，能自动发现周期性、节律与行为模式（适用于攻击追踪、用户行为分析、设备心跳监测等）。

- **极致性能与压缩**  
  实测 10⁶+ 事件下，存储与查询效率远超传统字符串日志。

- **极强迁移能力**  
  复合值指纹与业务语义解耦，跨系统、跨版本、跨项目零成本复用。

---

### 适用场景

- **网络安全与威胁狩猎**：复合攻击链还原、周期性 C2 检测、时区粗定位
- **大数据与用户行为分析**：多事件路径挖掘、营销漏斗优化
- **物联网与设备监控**：多维度异常复合状态追踪
- **灰产/反作弊**：多账号行为链路关联与模式识别
- **商业智能与运维**：任意复合指标的精确日志与分析

---

### 快速开始

```bash
pip install primelog
from primelog import PrimeLog

logger = PrimeLog()

# 记录任意复合事件
logger.record(
    caller="user_service",
    callee="payment_service",
    events=["timeout", "auth_failed", "high_risk_ip"]
)

logger.export()           # 导出 JSON / Wolfram Language
logger.analyze_patterns() # 自动挖掘组合模式与时间周期
```
### 🚀 快速上手（当前开发预览版）

现在还没正式发布到 PyPI，所以最快的方式就是：

```bash
# 1. 克隆仓库
git clone https://github.com/你的用户名/PrimeLog.git
cd PrimeLog

# 2. 创建虚拟环境（强烈推荐，避免污染全局）
python -m venv venv
source venv/bin/activate    # Linux/Mac
venv\Scripts\activate       # Windows

# 3. 安装依赖（如果有 requirements.txt 就用这个）
pip install -r requirements.txt

# 如果暂时没写 requirements.txt，就手动装核心的几个
pip install numpy pandas pyarrow scipy matplotlib

# 4. 可编辑安装（这样改代码不用重装）
pip install -e .

# 5. 直接跑例子（假设你有 demo/ 目录）
python demo/basic_usage.py
---
```
### License

PrimeLog 默认采用 **Mozilla Public License 2.0 (MPL 2.0)** 开源。

- 开源、个人、研究、非商业使用完全免费
- 商业闭源集成、企业 SaaS、生产环境部署请联系作者获取商业许可

PrimeLog™ 是 RoseHammer 的注册商标。

---

**Made with ❤️ by RoseHammer**

Decompose Anything. Understand Everything.

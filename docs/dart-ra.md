# DART 实现说明(内部记录,如实版)

日期:2026-09-07。对应二进制 `27c32a8f…`(dart 批为 `3631096f…`),分支 `dart-ra-baseline`,
补丁源码 `apply_dart_patch.py`(纯增量、锚点式、幂等,不触碰任何既有 CC 模式的代码路径)。

---

## 一、直接回答:这不是论文原生的 DART

**不是。** 我们实现的是 DART 的**接收端拥塞半侧**(receiver-driven direct rate
allocation),并且把控制通道**理想化**了。原论文的另一半——**网内偏转
(in-network deflection)——完全没有实现**。准确的称呼是
"DART-RA(接收端分配,简化/理想化实现)"。

原论文:Xue et al., *DART: Divide and Specialize for Fast Response to Congestion
in RDMA-Based Datacenter Networks*, IEEE/ACM Transactions on Networking, 2020。
其核心思想是把拥塞**按位置二分并分而治之**:

| 原论文 DART | 处理机制 | 我们的实现 |
|---|---|---|
| **接收端拥塞**(incast,多数情形) | 接收端知道有多少发送方,**直接计算并下发速率**(免迭代探测) | ✅ 实现(见下),但控制通道理想化 |
| **网内拥塞**(空间局部、少数情形) | 交换机**将包偏转**到备选路径 + RDMA 乱序处理 | ❌ 未实现 |
| 控制消息 | 真实报文:占带宽、有排队、可丢失 | ❌ 理想化:固定延迟、零带宽、不丢 |
| 交换机改动 | 需要(偏转逻辑) | ❌ 无任何交换机改动 |

### 简化的方向性(这一点对实验结论很重要)

所有简化都朝**有利于 DART** 的方向:

1. **理想化控制通道**是真实实现的**性能上界**——真实控制报文会占带宽、会排队、
   会丢,只会更慢更抖;
2. **未实现偏转半侧**在我们的实验里**不构成劣势**:S1–S6 的瓶颈全部在接收端
   接入链路(单收端或双收端),正是接收端拥塞主导的场景,偏转半侧本来就不该
   被触发。换言之,我们把 DART 放在**它最擅长的战场**上测;
3. 起步速率使用**先验组规模提示**(oracle N),等价于假设应用层把 incast 组大小
   提前告知了传输层——这是比原文更强的假设,进一步抬高其表现。

因此实验中 CBAP 相对 dart 的每一分优势,都是在 DART 拿到**上界待遇**的前提下
取得的——这个方向的简化让对比对 CBAP 而言是**保守**的(结论只会更稳,不会虚高)。
反过来也必须承认:**不能**声称"与完整 DART 比较过",发表表述只能限定在
接收端速率分配这一机制族;网内拥塞场景(瓶颈在核心/聚合层)下它的表现
**本包数据回答不了**。

### 原生 DART 部件清单(逐项:有 / 无)

| # | 原生 DART 部件(概述) | 我们 | 无的后果 |
|---|---|---|---|
| 1 | 接收端拥塞:接收端按发送方数量直接算速率下发 | ✅ 有(等分 α·C/n) | — |
| 2 | 速率通告的真实控制报文(占带宽、排队、可丢) | ❌ 理想化 | 上界待遇,真实实现只会更差 |
| 3 | **网内偏转**:交换机把拥塞点的包偏转到备选路径 | ❌ 无 | 网内拥塞场景不可测 |
| 4 | **偏转的保序处理**:吸收偏转造成的乱序,避免触发 RoCE go-back-N 大重传 | ❌ 无(无偏转即无乱序源,从未被考验) | 同上;且我们的数据不能证明"偏转代价小" |
| 5 | **DCQCN 回退**:两个专化机制覆盖不到的情形回退 ECN/CNP 反馈环 | ❌ 无 | mode 40 无 CNP 处理分支;交换机照常标 ECN、CNP 到达发送端被无视 |
| 6 | 拥塞位置判别(接收端 vs 网内,决定走哪条机制) | ❌ 无(恒走接收端分配) | 实验场景瓶颈全在接收端,判别恰好不需要;换场景即失效 |
| 7 | 新流起步策略 | ⚠️ 替代:oracleN 先验(α·C/N)或线速 | oracle 是比原文更强的假设(应用提前告知组规模) |
| 8 | 交换机改动 | ❌ 零改动 | — |

一句话:**8 个部件只有 1 个照实现了(再加 1 个用更强假设替代)**,其余 6 个
——包括你问的 DCQCN 回退与保序偏转——全部没有。这就是必须叫
"DART-RA 简化/理想化"而非"DART"的原因。

---

## 二、实现代码逻辑(完整)

### 2.1 接入点(全部 mode-gated,不影响其他算法)

新增 `CC_MODE_DART_RA = 40`(`rdma-hw.h` 枚举)。三个接入点:

```
AddQueuePair()   ── 发送端 QP 建立时:注册到 s_dartSenders;
│                   若 oracleN>0,起步速率 = alpha × C / oracleN(否则 RoCE 线速起步)
ReceiveUdp()     ── 接收端每收到一个数据包:调 DartOnReceiverData(ch)
third.cc 主流程  ── 配置解析(6 个键)+ SeedManager 之前调 SetDartConfig()
                    + ROUND_MODE 白名单加入 mode 40(third.cc:4302)
```

### 2.2 数据结构(静态,进程级)

```cpp
struct DartCfg {                    // 全局配置(SetDartConfig 填充)
    double   alpha;                 // 分配利用率目标
    uint64_t activeTimeoutNs;       // 活跃流滑动窗口
    uint64_t minIntervalNs;         // 接收端两次重算的最小间隔
    uint64_t ctrlDelayNs;           // 理想控制通道单向延迟
    uint64_t minRateBps;            // 每流分配下限
    uint32_t oracleN;               // 组规模先验(0 = 关闭,线速起步)
};

struct DartSenderRef { RdmaHw *hw; Ptr<RdmaQueuePair> qp;
                       uint64_t lastSeenNs, allocBps; };
std::map<uint64_t, DartSenderRef> s_dartSenders;   // 流键 → 发送端引用
                                                    // 流键 = sip<<32 | sport<<16 | dport

struct DartRecvState { uint64_t lastUpdateNs;
                       std::map<uint64_t,uint64_t> lastSeen; }; // 流键 → 最近数据到达时刻
std::map<uint32_t, DartRecvState> s_dartRecv;      // 按接收端节点 id(天然支持多接收端)
```

### 2.3 接收端主循环 `DartOnReceiverData(ch)`(逐步)

每个到达的数据包触发一次(未注册的流直接返回):

```
1. 记录该流的 lastSeen[key] = now
2. 限频:now − lastUpdateNs < minIntervalNs → 返回(避免每包重算)
3. 取本包到达的 NIC 的线速 C(= 接收端接入链路容量,自动适配 10/200/400G)
4. 数活跃流:n = |{ f : now − lastSeen[f] ≤ activeTimeoutNs }|
5. 等分分配:alloc = alpha × C / n,下限钳制 max(alloc, minRateBps)
6. 对每条活跃流:
     若 alloc == 该流上次下发值 → 跳过(去重,不发无变化的控制消息)
     否则 Simulator::Schedule(ctrlDelayNs, DartDeliverRate, hw, qp, alloc)
        └ DartDeliverRate:qp 未完成时 hw->ChangeRate(qp, alloc)  ← 理想化在此:
          固定延迟、不占带宽、不丢失
```

### 2.4 发送端起步(oracle 分支)

`AddQueuePair()` 内(建 QP 即注册):

```cpp
if (oracleN > 0) {
    init = alpha * C / oracleN;            // 组规模先验起步
    if (init < minRateBps) init = minRateBps;
    qp->m_rate = init;  ref.allocBps = init;
}   // oracleN == 0 时不动 qp->m_rate,即沿用 RoCE 默认的线速起步
```

已验证起步值存活至发送(round_summary.start_rate = 5.85G = 0.95×400G/65,分毫不差)。

### 2.5 配置键(third.cc 解析,发布包 configs/ 里可见)

| 键 | 本包取值 | 语义 |
|---|---|---|
| `CC_MODE` | 40 | 选择 DART-RA 模式 |
| `DART_ALPHA` | 0.85 | 分配利用率(留 1−α 余量防队列) |
| `DART_ACTIVE_TIMEOUT_US` | 100 | 活跃流窗口:多久没来数据算退出 |
| `DART_UPDATE_MIN_INTERVAL_US` | 10 | 接收端重算最小间隔 |
| `DART_CTRL_DELAY_US` | 6 | 理想控制通道延迟(≈ 半 RTT 量级) |
| `DART_ORACLE_N` | 65(S5=33,S6=31) | 组规模先验 = 该接收端的流数(incast+背景) |
| `DART_MIN_RATE_MBPS` | 100 | 每流下限(与基线 MIN_RATE 一致) |

### 2.6 已知行为特性(实现决定的,非 bug)

- **mean ≈ p99 ≈ CCT 锁步**:等分分配让全体成员几乎同时完成——这是该机制的
  签名,不是统计巧合;
- 活跃流计数由**数据到达驱动**:某流完成后要等 activeTimeout 才从分母退出,
  期间余量略保守;
- 控制消息仅在分配值**变化**时下发(去重),稳态零消息;
- 双接收端(S6)天然各自独立分配(state 按节点 id 分桶),无需跨接收端协调;
- 确定性:无随机源,同配置同种子逐字节可复现。

### 2.7 验证链

1. **回归门**:打补丁后的二进制对旧 CBAP(19/19)、DCQCN(11/11)结果
   **逐文件字节级相同**——证明未扰动任何既有模式;
2. **起步值审计**:round_summary.start_rate 与 α·C/N 精确吻合;
3. **行为签名**:10G 下稳定付出 ≈1/α 的完成时间税(α=0.85 → 慢约 17%,
   α=0.95 → 慢约 4.8%),与理论预期一致。

---

## 三、发表时的表述边界(建议,底线)

可以说:
- "与一个**接收端驱动直接速率分配**的对照(DART 风格的接收端拥塞处理机制,
  理想化控制通道,构成该类机制的性能上界)比较";
- "该对照在零 PFC/低队列条件下较 CBAP 慢 15–17%(α=0.85 配置)"。

不能说:
- "实现/复现了 DART"或"与 DART(完整系统)比较"——偏转半侧与真实控制
  通道均未实现,审稿人查证代码即穿帮;
- 不宜在网内拥塞场景下引用本对照的数字(实验里不存在这类场景)。

发布数据包(`CBAP_EXPERIMENTS_FINAL_20260907.zip`)按你的决定只含 α=0.85 一档、
标签为 `dart`;全量档案(三档变体 + 实现披露)在
`CBAP_SUPPLEMENT_DART_SWEEP_DUALBTLNK_20260907.zip`,建议永久留底——
它是审稿质询时的证据链。

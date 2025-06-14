# 🥊 AI模型对战系统

一个让多个AI模型对同一问题进行对战、互相评分的系统。各模型会给出自己的回答，并对其他模型的回答进行打分，最终选出总分最高的获胜者。

## ✨ 主要特性

- **模型互评机制**: 每个模型既是回答者也是评审员
- **多轮对战**: 支持多轮次对战，累计得分
- **标准化评分**: 统一的100分制评分标准
- **详细分析**: 包含评分理由和详细分析
- **结果保存**: 完整保存对战过程和结果

## 🛠️ 安装依赖

```bash
pip install dashscope python-dotenv
```

## 🔧 配置

### 1. API密钥配置
创建 `.env` 文件并设置DashScope API密钥：

```bash
DASHSCOPE_API_KEY=your_dashscope_api_key_here
```

### 2. 支持的模型

- `qwen-turbo` - 通义千问Turbo版本
- `qwen-max` - 通义千问Max版本  
- `qwen-vl-max` - 通义千问视觉理解版本
- `qwen-audio-turbo-latest` - 通义千问音频理解版本

## 📊 评分标准

系统采用100分制评分，包含三个维度：

1. **准确性和完整性 (40分)** - 回答与问题的相关程度
2. **逻辑性和结构性 (30分)** - 回答的完整性和结构化程度  
3. **创新性和深度 (30分)** - 独特见解和深入分析

最终得分为100分制，获胜者为总分最高的模型。

## 🔧 使用示例

### 独立运行模型对战
```bash
python model_battle.py
# 选择模式 (1: 简单演示, 2: 完整对战)
```

### 测试功能
```bash
python test_model_battle.py
```

### 通过MCP客户端使用
```bash
uv run cli/client.py server/server.py
# 然后可以调用模型对战工具
```

## 📈 对战结果格式

```json
{
  "question": "问题内容",
  "final_winner": "qwen-max",
  "final_scores": {
    "qwen-turbo": 158.5,
    "qwen-max": 172.3
  },
  "final_answer": "获胜模型的回答内容",
  "timestamp": "2025-01-07 23:45:00",
  "rounds_count": 2
}
```

## 🏆 实际应用场景

1. **研究不同模型的表现差异**
2. **为特定任务选择最适合的模型**
3. **比较模型在不同领域的专业能力**
4. **验证模型输出的一致性和准确性**
5. **优化prompt策略**

## 🔄 对战流程

1. **初始回答**: 所有模型回答同一问题
2. **互相评分**: 每个模型对其他模型的回答进行评分
3. **统计得分**: 计算每个模型在本轮的平均得分
4. **多轮重复**: 默认进行2轮对战
5. **确定获胜者**: 选择总分最高的模型

## 📋 可用工具

### MCP工具列表

- `ai_model_battle` - 通用模型对战
- `health_advice_battle` - 健康建议对战
- `nutrition_analysis_battle` - 营养分析对战

## 🛡️ 注意事项

- 确保DashScope API密钥有效且有足够的配额
- 某些模型可能有访问限制或地区限制
- 建议在正式使用前先进行小规模测试
- 模型对战结果会保存到本地文件，注意存储空间

## 🎉 开始使用

1. 配置DashScope API密钥
2. 安装依赖：`pip install dashscope python-dotenv`
3. 运行测试：`python test_model_battle.py`
4. 运行模型对战：`python model_battle.py`
5. 或者启动MCP服务器：`uv run cli/client.py server/server.py`

享受AI模型对战的乐趣吧！🚀 
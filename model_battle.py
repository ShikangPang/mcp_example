import asyncio
import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import statistics

from dashscope import Generation
import os
from dotenv import load_dotenv

load_dotenv()

class ModelType(Enum):
    DASHSCOPE_QWEN_AUDIO_TURBO_LATEST = "qwen-audio-turbo-latest"
    DASHSCOPE_QWEN_VL_MAX = "qwen-vl-max"
    DASHSCOPE_QWEN = "qwen-turbo"
    DASHSCOPE_QWEN_MAX = "qwen-max"

@dataclass
class ModelResponse:
    model_name: str
    model_type: ModelType
    response: str
    response_time: float
    scores: Dict[str, Any] = None  # 其他模型给出的分数和评价
    token_count: Optional[int] = None
    error: Optional[str] = None

@dataclass
class BattleRound:
    round_number: int
    responses: List[ModelResponse]
    scores: Dict[str, float]  # 每个模型在这一轮的总得分

@dataclass
class BattleResult:
    question: str
    rounds: List[BattleRound]
    final_scores: Dict[str, float]  # 总得分
    final_winner: str
    final_answer: str
    timestamp: str

class ModelBattle:
    def __init__(self):
        self.setup_clients()
        
    def setup_clients(self):
        """设置DashScope API密钥"""
        dashscope_api_key = os.getenv('DASHSCOPE_API_KEY')
        if dashscope_api_key:
            os.environ['DASHSCOPE_API_KEY'] = dashscope_api_key
        else:
            print("⚠️  警告: 未找到DASHSCOPE_API_KEY环境变量")

    async def call_model(self, model_type: ModelType, prompt: str) -> ModelResponse:
        """调用DashScope模型"""
        return await self.call_dashscope_model(model_type, prompt)

    async def call_dashscope_model(self, model_type: ModelType, prompt: str) -> ModelResponse:
        """调用DashScope模型"""
        start_time = time.time()
        try:
            response = Generation.call(
                model=model_type.value,
                prompt=prompt,
                max_tokens=1000,
                temperature=0.7
            )
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                content = response.output.text
                token_count = response.usage.total_tokens if hasattr(response, 'usage') else None
                
                return ModelResponse(
                    model_name=model_type.value,
                    model_type=model_type,
                    response=content,
                    response_time=response_time,
                    token_count=token_count,
                    scores={}
                )
            else:
                return ModelResponse(
                    model_name=model_type.value,
                    model_type=model_type,
                    response="",
                    response_time=response_time,
                    error=f"API错误 (状态码: {response.status_code}): {response.message}",
                    scores={}
                )
                
        except Exception as e:
            return ModelResponse(
                model_name=model_type.value,
                model_type=model_type,
                response="",
                response_time=time.time() - start_time,
                error=f"调用失败: {str(e)}",
                scores={}
            )

    def generate_scoring_prompt(self, question: str, response: ModelResponse) -> str:
        """生成评分提示"""
        return f"""请对以下AI回答进行评分和简要评价。评分标准如下：
1. 准确性和完整性 (40分)：回答是否准确、全面地解答了问题
2. 逻辑性和结构性 (30分)：论述是否清晰、有条理
3. 创新性和深度 (30分)：是否有独特见解和深入分析

问题：{question}

回答内容：
{response.response}

请给出总分(0-100分)和简短评价。
格式要求：只需要返回一个JSON字符串，包含score和comment两个字段，例如：
{{"score": 85, "comment": "回答准确全面，逻辑清晰，但创新性略显不足"}}"""

    async def score_response(self, question: str, response: ModelResponse, scorer_model: ModelType) -> Dict[str, Any]:
        """让一个模型对另一个模型的回答进行评分"""
        scoring_prompt = self.generate_scoring_prompt(question, response)
        scoring_response = await self.call_model(scorer_model, scoring_prompt)
        
        if scoring_response.error:
            return {"score": 0, "comment": f"评分失败: {scoring_response.error}"}
        
        try:
            # 尝试解析JSON响应
            result = json.loads(scoring_response.response)
            return {
                "score": float(result.get("score", 0)),
                "comment": result.get("comment", "无评价")
            }
        except json.JSONDecodeError:
            # 如果不是JSON格式，尝试提取数字
            import re
            score_match = re.search(r'(\d+(?:\.\d+)?)', scoring_response.response)
            score = float(score_match.group(1)) if score_match else 0
            return {
                "score": score,
                "comment": scoring_response.response[:100] + "..." if len(scoring_response.response) > 100 else scoring_response.response
            }
        except Exception as e:
            return {"score": 0, "comment": f"评分解析错误: {str(e)}"}

    async def battle_round(self, round_number: int, question: str, models: List[ModelType]) -> BattleRound:
        """执行一轮对战"""
        print(f"\n🔄 第 {round_number} 轮对战开始")
        print(f"📝 问题: {question}")
        print("-" * 60)
        
        # 获取所有模型的回答
        print("🤖 正在获取各模型回答...")
        tasks = [self.call_model(model, question) for model in models]
        responses = await asyncio.gather(*tasks)
        
        # 显示每个模型的回答
        for response in responses:
            print(f"\n🤖 {response.model_name}:")
            if response.error:
                print(f"❌ 错误: {response.error}")
            else:
                print(f"⏱️  响应时间: {response.response_time:.2f}秒")
                print(f"💬 回答: {response.response[:200]}...")
        
        # 检查是否有有效回答
        valid_responses = [r for r in responses if not r.error]
        if len(valid_responses) < 2:
            print("⚠️  警告: 有效回答不足，无法进行评分")
            round_scores = {r.model_name: 0 for r in responses}
            return BattleRound(
                round_number=round_number,
                responses=responses,
                scores=round_scores
            )
        
        # 让每个模型对其他模型的回答进行评分
        print("\n📊 开始互相评分...")
        for i, response in enumerate(responses):
            if response.error:
                response.scores = {}
                continue
                
            response.scores = {}
            for j, scorer_model in enumerate(models):
                if i != j:  # 不给自己打分
                    print(f"   {scorer_model.value} 正在评分 {response.model_name}...")
                    score_result = await self.score_response(question, response, scorer_model)
                    response.scores[scorer_model.value] = score_result
                    
                    print(f"📊 {scorer_model.value} 对 {response.model_name} 的评分:")
                    print(f"   分数: {score_result['score']}")
                    print(f"   评价: {score_result['comment']}")
        
        # 计算每个模型的总分
        round_scores = {}
        for response in responses:
            if not response.error and response.scores:
                # 计算平均分
                scores = [score_result["score"] for score_result in response.scores.values()]
                round_scores[response.model_name] = sum(scores) / len(scores) if scores else 0
            else:
                round_scores[response.model_name] = 0
        
        return BattleRound(
            round_number=round_number,
            responses=responses,
            scores=round_scores
        )

    async def battle(self, question: str, models: List[ModelType], num_rounds: int = 2) -> BattleResult:
        """执行多轮对战"""
        print("🎯 开始模型对战！")
        print(f"🤖 参与模型: {[model.value for model in models]}")
        
        rounds = []
        
        for round_num in range(num_rounds):
            round_result = await self.battle_round(round_num + 1, question, models)
            rounds.append(round_result)
            
            # 显示本轮得分
            print(f"\n📊 第 {round_num + 1} 轮得分:")
            for model_name, score in round_result.scores.items():
                print(f"   {model_name}: {score:.2f}")
            
            if round_num < num_rounds - 1:
                print("\n⏳ 等待3秒后开始下一轮...")
                await asyncio.sleep(3)
        
        # 计算总分并确定获胜者
        final_scores = {}
        for model_type in models:
            model_name = model_type.value
            scores = [round_result.scores.get(model_name, 0) for round_result in rounds]
            final_scores[model_name] = sum(scores)
        
        if final_scores:
            winner = max(final_scores.items(), key=lambda x: x[1])[0]
        else:
            winner = "无获胜者"
        
        # 获取获胜者的最后一轮回答作为最终答案
        final_answer = ""
        if winner != "无获胜者":
            for response in rounds[-1].responses:
                if response.model_name == winner and not response.error:
                    final_answer = response.response
                    break
        
        result = BattleResult(
            question=question,
            rounds=rounds,
            final_scores=final_scores,
            final_winner=winner,
            final_answer=final_answer,
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S')
        )
        
        self.display_battle_result(result)
        return result

    def display_battle_result(self, result: BattleResult):
        """显示对战结果"""
        print("\n" + "="*80)
        print("🏁 对战最终结果")
        print("="*80)
        print(f"📝 问题: {result.question}")
        print(f"🏆 最终获胜者: {result.final_winner}")
        
        print("\n📈 总得分排行:")
        sorted_scores = sorted(result.final_scores.items(), key=lambda x: x[1], reverse=True)
        for i, (model_name, score) in enumerate(sorted_scores, 1):
            print(f"   {i}. {model_name}: {score:.2f}")
        
        if result.final_answer:
            print("\n💡 获胜答案:")
            print(result.final_answer)
        print("="*80)

    def save_battle_result(self, result: BattleResult, filename: str = "battle_result.json"):
        """保存对战结果到文件"""
        data = {
            "question": result.question,
            "final_winner": result.final_winner,
            "final_scores": result.final_scores,
            "final_answer": result.final_answer,
            "timestamp": result.timestamp,
            "rounds": [
                {
                    "round_number": round_result.round_number,
                    "scores": round_result.scores,
                    "responses": [
                        {
                            "model_name": response.model_name,
                            "response": response.response,
                            "scores": response.scores,
                            "response_time": response.response_time,
                            "token_count": response.token_count,
                            "error": response.error
                        }
                        for response in round_result.responses
                    ]
                }
                for round_result in result.rounds
            ]
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 对战结果已保存到 {filename}")

async def run_battle_demo():
    """运行对战演示"""
    battle = ModelBattle()
    
    question = "请详细分析人工智能在医疗领域的应用前景、挑战和伦理考虑。"
    models = [
        ModelType.DASHSCOPE_QWEN,
        ModelType.DASHSCOPE_QWEN_MAX,
        # ModelType.DASHSCOPE_QWEN_VL_MAX,  # 如果需要视觉模型可以启用
    ]
    
    result = await battle.battle(question, models)
    battle.save_battle_result(result)

async def run_simple_demo():
    """运行简单演示（只用文本模型）"""
    battle = ModelBattle()
    
    question = "请用100字左右简单介绍什么是人工智能。"
    models = [
        ModelType.DASHSCOPE_QWEN,
        ModelType.DASHSCOPE_QWEN_MAX,
        ModelType.DASHSCOPE_QWEN_VL_MAX,
        ModelType.DASHSCOPE_QWEN_AUDIO_TURBO_LATEST
    ]
    
    result = await battle.battle(question, models, num_rounds=1)
    battle.save_battle_result(result, "simple_battle_result.json")

if __name__ == "__main__":
    print("🚀 启动AI模型对战系统...")
    
    # 选择运行模式
    mode = input("选择模式 (1: 简单演示, 2: 完整对战): ").strip()
    
    if mode == "1":
        asyncio.run(run_simple_demo())
    else:
        asyncio.run(run_battle_demo()) 
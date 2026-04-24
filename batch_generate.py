"""
批量图像生成测试脚本 - 使用 gemini-3-pro-image-preview 异步接口
"""

import asyncio
import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")
API_BASE = os.getenv("API_BASE", "https://api.tu-zi.com")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
}

DEFAULT_PROMPT = "a serene mountain lake at sunrise, photorealistic"
DEFAULT_COUNT = 4
DEFAULT_SIZE = "1x1"


async def submit_task(client: httpx.AsyncClient, prompt: str, index: int) -> dict:
    """提交图像生成任务"""
    data = {
        "model": "gemini-3-pro-image-preview",
        "prompt": prompt,
        "size": DEFAULT_SIZE,
        "response_format": "url",
    }
    endpoint = f"{API_BASE}/v1/images/generations"
    resp = await client.post(endpoint, json=data, headers=HEADERS)
    resp.raise_for_status()
    result = resp.json()

    images = result.get("data")
    if isinstance(images, list) and images:
        image_url = images[0].get("url")
        print(f"[{index+1}] 同步生成完成 | 提示词: {prompt[:30]}...")
        return {"index": index, "prompt": prompt, "url": image_url, "status": "completed"}

    task_id = result.get("task_id") or result.get("job_id") or result.get("id")
    if not task_id:
        raise ValueError(f"无法从响应中识别任务ID或图片结果: {result}")

    print(f"[{index+1}] 任务已提交: {task_id} | 提示词: {prompt[:30]}...")
    return {"index": index, "task_id": task_id, "prompt": prompt, "status": "submitted"}


async def poll_task(client: httpx.AsyncClient, task: dict, interval: int = 3) -> dict:
    """轮询任务状态直到完成"""
    if task.get("status") == "completed" and task.get("url"):
        return task

    task_id = task["task_id"]
    index = task["index"]
    endpoint = f"{API_BASE}/v1/images/generations/{task_id}"

    while True:
        resp = await client.get(endpoint, headers=HEADERS)
        resp.raise_for_status()
        result = resp.json()
        status = result.get("status")
        progress = result.get("progress", 0)

        print(f"[{index+1}] 任务 {task_id} | 状态: {status} | 进度: {progress}%")

        if status == "completed":
            image_url = result.get("image_url") or result.get("url") or result.get("video_url")
            print(f"[{index+1}] 完成! 图像URL: {image_url}")
            return {"index": index, "prompt": task["prompt"], "url": image_url, "status": "completed"}

        if status == "failed":
            print(f"[{index+1}] 任务失败: {task_id}")
            return {"index": index, "prompt": task["prompt"], "url": None, "status": "failed"}

        await asyncio.sleep(interval)


async def batch_generate(prompts: list[str]) -> list[dict]:
    """并发提交所有任务，然后并发轮询"""
    timeout = httpx.Timeout(connect=10, read=120, write=30, pool=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # 并发提交所有任务
        print(f"\n=== 提交 {len(prompts)} 个任务 ===")
        tasks = await asyncio.gather(*[
            submit_task(client, prompt, i) for i, prompt in enumerate(prompts)
        ])

        # 并发轮询所有任务
        submitted_tasks = [task for task in tasks if task.get("status") == "submitted"]
        if submitted_tasks:
            print(f"\n=== 开始轮询任务状态（每interval秒检查一次）===")
            polled_results = await asyncio.gather(*[
                poll_task(client, task) for task in submitted_tasks
            ])
            completed_results = [task for task in tasks if task.get("status") == "completed"]
            results = sorted(completed_results + polled_results, key=lambda item: item["index"])
        else:
            results = tasks

    return results


def collect_generation_request() -> tuple[str, int]:
    """读取最小化验证所需的提示词和数量"""
    print("请输入同一个提示词，脚本会并发生成多张图片供你选择。")

    raw_prompt = input(f"提示词（直接回车使用默认值）[{DEFAULT_PROMPT}]: ").strip()
    prompt = raw_prompt or DEFAULT_PROMPT

    raw_count = input(f"生成数量（1-20，默认 {DEFAULT_COUNT}）: ").strip()
    if not raw_count:
        return prompt, DEFAULT_COUNT

    try:
        count = int(raw_count)
    except ValueError:
        print("数量格式无效，已使用默认值。")
        return prompt, DEFAULT_COUNT

    if count < 1 or count > 20:
        print("数量超出范围，已使用默认值。")
        return prompt, DEFAULT_COUNT

    return prompt, count


def main():
    if not API_KEY or API_KEY == "sk-your-api-key-here":
        print("错误: 请在 .env 文件中设置有效的 API_KEY")
        return

    prompt, count = collect_generation_request()
    prompts = [prompt] * count

    start = time.time()
    print(f"\n开始批量生成，共 {count} 张图像")
    print(f"统一提示词: {prompt}")
    print(f"图像比例: {DEFAULT_SIZE}")

    results = asyncio.run(batch_generate(prompts))

    elapsed = time.time() - start
    success = sum(1 for r in results if r["status"] == "completed")

    print(f"\n=== 完成 ===")
    print(f"成功: {success}/{len(results)} | 耗时: {elapsed:.1f}s")
    for r in results:
        status_icon = "✓" if r["status"] == "completed" else "✗"
        print(f"  {status_icon} [{r['index']+1}] {r['prompt'][:40]}...")
        if r["url"]:
            print(f"       {r['url']}")


if __name__ == "__main__":
    main()

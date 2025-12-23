import json
import os


def count_fragment_length_distribution(json_file_path):
    """
    统计 JSON 文件中「片段内容」的长度分布（每200字一档）
    :param json_file_path: 你的 JSON 文件路径
    """
    # 初始化统计字典（档名: 数量），支持自动扩展档数
    length_stats = {}

    # 读取 JSON 文件
    if not os.path.exists(json_file_path):
        print(f"❌ 找不到文件：{json_file_path}")
        return

    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            fragments = json.load(f)
        print(f"✅ 成功读取 JSON 文件，共 {len(fragments)} 条片段")
    except json.JSONDecodeError:
        print(f"❌ JSON 格式错误：{json_file_path}")
        return
    except Exception as e:
        print(f"❌ 读取文件失败：{str(e)}")
        return

    # 遍历每条片段，统计长度
    for idx, frag in enumerate(fragments, 1):
        # 获取片段内容，若不存在则视为 0 字
        fragment_content = frag.get("片段内容", "").strip()
        content_length = len(fragment_content)

        # 计算所属档位（每200字一档，如 0-200、200-400...）
        bin_start = (content_length // 200) * 200
        bin_end = bin_start + 200
        bin_key = f"{bin_start}-{bin_end}"

        # 更新统计数量
        length_stats[bin_key] = length_stats.get(bin_key, 0) + 1

    # 按档位排序（确保 0-200、200-400... 顺序输出）
    sorted_bins = sorted(length_stats.keys(), key=lambda x: int(x.split('-')[0]))

    # 输出结果
    print("\n" + "=" * 30)
    print("片段内容长度分布统计（每200字一档）")
    print("=" * 30)
    for bin_key in sorted_bins:
        count = length_stats[bin_key]
        print(f"{bin_key:8s} {count:4d} 个")

    # 输出总计（验证是否与总片段数一致）
    total_count = sum(length_stats.values())
    print("=" * 30)
    print(f"总计：{total_count} 个片段")
    print("=" * 30)


# ================= 主执行入口 =================
if __name__ == "__main__":
    # 替换为你的 JSON 文件路径（单个文件）
    TARGET_JSON_PATH = r"G:\KnowledgeBase\knowledgebase_segmentation_original\药典临床用药须知（化学药和生物制品卷 2020版）.json"

    # 执行统计
    count_fragment_length_distribution(TARGET_JSON_PATH)

    # 如果需要统计文件夹下所有 JSON 文件，取消下面注释并替换为文件夹路径
    # TARGET_JSON_FOLDER = r"G:\KnowledgeBase\knowledgebase_segmentation_original"
    # for filename in os.listdir(TARGET_JSON_FOLDER):
    #     if filename.lower().endswith('.json') and not filename.startswith('~$'):
    #         json_path = os.path.join(TARGET_JSON_FOLDER, filename)
    #         print(f"\n\n===== 统计文件：{filename} =====")
    #         count_fragment_length_distribution(json_path)
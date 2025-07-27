#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试运行脚本
提供便捷的测试执行和管理功能
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description=""):
    """运行命令并处理结果"""
    print(f"\n{'='*60}")
    if description:
        print(f"执行: {description}")
    print(f"命令: {' '.join(cmd)}")
    print('='*60)
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print(f"\n✅ {description or '命令'} 执行成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {description or '命令'} 执行失败，退出码: {e.returncode}")
        return False
    except Exception as e:
        print(f"\n❌ 执行出错: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(description="测试运行工具")
    
    # 测试范围选项
    parser.add_argument(
        "--module", "-m",
        choices=["douyin", "bilibili", "music", "xiaohongshu", "telegram", "public"],
        help="运行特定模块的测试"
    )
    
    # 测试类型选项
    parser.add_argument(
        "--type", "-t",
        choices=["unit", "integration", "all"],
        default="all",
        help="测试类型 (默认: all)"
    )
    
    # 详细程度选项
    parser.add_argument(
        "--verbose", "-v",
        action="count",
        default=0,
        help="详细输出级别 (-v, -vv, -vvv)"
    )
    
    # 快速模式
    parser.add_argument(
        "--fast", "-f",
        action="store_true",
        help="快速模式，跳过慢速测试"
    )
    
    # 覆盖率报告
    parser.add_argument(
        "--coverage", "-c",
        action="store_true",
        help="生成覆盖率报告"
    )
    
    # 并行测试
    parser.add_argument(
        "--parallel", "-p",
        type=int,
        help="并行测试进程数"
    )
    
    # 失败时停止
    parser.add_argument(
        "--stop-on-first-failure", "-x",
        action="store_true",
        help="首次失败时停止"
    )
    
    # 只显示失败的测试
    parser.add_argument(
        "--failed-only",
        action="store_true",
        help="只重新运行上次失败的测试"
    )
    
    # 生成测试报告
    parser.add_argument(
        "--report",
        action="store_true",
        help="生成HTML测试报告"
    )
    
    # 清理选项
    parser.add_argument(
        "--clean",
        action="store_true",
        help="清理测试缓存和临时文件"
    )
    
    args = parser.parse_args()
    
    # 获取项目根目录
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # 清理操作
    if args.clean:
        print("🧹 清理测试缓存和临时文件...")
        clean_commands = [
            ["find", ".", "-type", "d", "-name", "__pycache__", "-exec", "rm", "-rf", "{}", "+"] if os.name != 'nt' else ["powershell", "-Command", "Get-ChildItem -Path . -Recurse -Name '__pycache__' | Remove-Item -Recurse -Force"],
            ["find", ".", "-name", "*.pyc", "-delete"] if os.name != 'nt' else ["powershell", "-Command", "Get-ChildItem -Path . -Recurse -Name '*.pyc' | Remove-Item -Force"],
            ["rm", "-rf", ".pytest_cache"] if os.name != 'nt' else ["powershell", "-Command", "Remove-Item -Path '.pytest_cache' -Recurse -Force -ErrorAction SilentlyContinue"]
        ]
        
        for cmd in clean_commands:
            try:
                subprocess.run(cmd, check=False, capture_output=True)
            except:
                pass
        print("✅ 清理完成")
        return
    
    # 构建pytest命令
    cmd = ["python", "-m", "pytest"]
    
    # 添加详细程度
    if args.verbose:
        cmd.append("-" + "v" * min(args.verbose, 3))
    
    # 添加模块选择
    if args.module:
        module_map = {
            "douyin": "src/tests/test_douyin_download.py",
            "bilibili": "src/tests/test_bilibili_download.py", 
            "music": "src/tests/test_music_download.py",
            "xiaohongshu": "src/tests/test_xiaohongshu_download.py",
            "telegram": "src/tests/test_telegram_bot.py",
            "public": "src/tests/test_public_methods.py"
        }
        cmd.append(module_map[args.module])
    else:
        cmd.append("src/tests/")
    
    # 添加测试类型标记
    if args.type != "all":
        cmd.extend(["-m", args.type])
    
    # 快速模式
    if args.fast:
        cmd.extend(["-m", "not slow"])
    
    # 并行测试
    if args.parallel:
        cmd.extend(["-n", str(args.parallel)])
    
    # 失败时停止
    if args.stop_on_first_failure:
        cmd.append("-x")
    
    # 只运行失败的测试
    if args.failed_only:
        cmd.append("--lf")
    
    # 覆盖率报告
    if args.coverage:
        cmd.extend([
            "--cov=src",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing",
            "--cov-report=xml"
        ])
    
    # HTML报告
    if args.report:
        cmd.extend([
            "--html=test_report.html",
            "--self-contained-html"
        ])
    
    # 执行测试
    success = run_command(cmd, "运行测试套件")
    
    if success:
        print(f"\n🎉 测试执行完成！")
        if args.coverage:
            print("📊 覆盖率报告已生成: htmlcov/index.html")
        if args.report:
            print("📋 测试报告已生成: test_report.html")
    else:
        print(f"\n💥 测试执行失败，请检查错误信息")
        sys.exit(1)


def show_test_info():
    """显示测试信息"""
    print("""
🧪 视频下载器测试套件
===================

可用的测试模块:
├── douyin      - 抖音下载模块测试 (27个测试用例)
├── bilibili    - B站下载模块测试 (28个测试用例)  
├── music       - 网易云音乐下载测试 (24个测试用例)
├── xiaohongshu - 小红书下载模块测试 (24个测试用例)
├── telegram    - Telegram机器人测试 (33个测试用例)
└── public      - 公共方法模块测试 (35个测试用例)

测试用例总数: 171个

使用示例:
  python run_tests.py                    # 运行所有测试
  python run_tests.py -m douyin          # 只测试抖音模块
  python run_tests.py -t unit            # 只运行单元测试
  python run_tests.py -f                 # 快速模式，跳过慢速测试
  python run_tests.py -c                 # 生成覆盖率报告
  python run_tests.py -x -v              # 详细输出，失败时停止
  python run_tests.py --clean            # 清理测试缓存

标记说明:
  @pytest.mark.unit          - 单元测试
  @pytest.mark.integration   - 集成测试
  @pytest.mark.slow          - 慢速测试
  @pytest.mark.network       - 需要网络连接
  @pytest.mark.file_system   - 需要文件系统操作
""")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        show_test_info()
    main()
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI工作流菜单初始化脚本

创建 "AI平台" 目录和 "流程编排" 菜单，并关联到管理员角色。

用法:
    python scripts/seed_ai_workflow_menus.py
"""
import asyncio
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nanoid import generate
from sqlalchemy import select
from app.database import AsyncSessionLocal
from core.menu.model import Menu
from core.role.model import Role


def auto_import_models():
    project_root = Path(__file__).parent.parent
    for scan_dir in ["core", "scheduler", "online_dev", "rag", "ai_workflow"]:
        scan_path = project_root / scan_dir
        if not scan_path.exists():
            continue
        for model_file in scan_path.rglob("*model.py"):
            relative_path = model_file.relative_to(project_root)
            module_path = str(relative_path.with_suffix("")).replace("/", ".").replace("\\", ".")
            try:
                importlib.import_module(module_path)
            except ImportError:
                pass


auto_import_models()


def gen_id() -> str:
    return generate(size=21)


AI_WORKFLOW_MENUS = [
    {
        "name": "AiPlatform",
        "title": "AI平台",
        "path": "/ai-platform",
        "type": "catalog",
        "icon": "lucide:bot",
        "order": 50,
        "is_system": True,
        "children": [
            {
                "name": "AiWorkflow",
                "title": "流程编排",
                "path": "/ai-platform/workflow",
                "type": "menu",
                "icon": "lucide:workflow",
                "component": "/_core/ai-workflow/index",
                "order": 1,
                "is_system": True,
            },
            {
                "name": "TeamManagement",
                "title": "团队管理",
                "path": "/ai-platform/team",
                "type": "menu",
                "icon": "lucide:users",
                "component": "/_core/ai-workflow/team/index",
                "order": 2,
                "is_system": True,
            },
        ],
    },
]


async def seed():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Role).where(Role.code == "admin")
        )
        admin_role = result.scalar_one_or_none()
        if not admin_role:
            print("错误: 未找到管理员角色 (code=admin)，请先初始化角色数据")
            return

        created_count = 0
        assigned_count = 0

        for catalog_def in AI_WORKFLOW_MENUS:
            result = await db.execute(
                select(Menu).where(
                    Menu.name == catalog_def["name"],
                    Menu.is_deleted.is_(False),
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                parent_id = existing.id
                print(f"目录已存在: {catalog_def['title']} ({existing.id})")
                if admin_role and existing not in admin_role.menus:
                    admin_role.menus.append(existing)
                    assigned_count += 1
            else:
                parent_id = gen_id()
                menu = Menu(
                    id=parent_id,
                    name=catalog_def["name"],
                    title=catalog_def["title"],
                    path=catalog_def["path"],
                    type=catalog_def["type"],
                    icon=catalog_def.get("icon"),
                    component=catalog_def.get("component"),
                    order=catalog_def.get("order", 0),
                    is_system=catalog_def.get("is_system", False),
                )
                db.add(menu)
                created_count += 1
                print(f"创建目录: {catalog_def['title']} ({parent_id})")
                if admin_role:
                    admin_role.menus.append(menu)
                    assigned_count += 1

            for child_def in catalog_def.get("children", []):
                result = await db.execute(
                    select(Menu).where(
                        Menu.name == child_def["name"],
                        Menu.is_deleted.is_(False),
                    )
                )
                existing_child = result.scalar_one_or_none()
                if existing_child:
                    print(f"  菜单已存在: {child_def['title']} ({existing_child.id})")
                    if child_def.get("component"):
                        existing_child.component = child_def["component"]
                    if admin_role and existing_child not in admin_role.menus:
                        admin_role.menus.append(existing_child)
                        assigned_count += 1
                    continue

                child_id = gen_id()
                menu = Menu(
                    id=child_id,
                    parent_id=parent_id,
                    name=child_def["name"],
                    title=child_def["title"],
                    path=child_def["path"],
                    type=child_def["type"],
                    icon=child_def.get("icon"),
                    component=child_def.get("component"),
                    order=child_def.get("order", 0),
                    is_system=child_def.get("is_system", False),
                )
                db.add(menu)
                created_count += 1
                print(f"  创建菜单: {child_def['title']} ({child_id})")
                if admin_role:
                    admin_role.menus.append(menu)
                    assigned_count += 1

        await db.commit()

        from utils.redis import CacheManager
        menu_cache = CacheManager(prefix="menu:")
        await menu_cache.delete_pattern("tree*")
        await menu_cache.delete_pattern("user_route:*")
        print("已清除菜单Redis缓存")

        print(f"\n完成: 创建 {created_count} 个菜单, 关联 {assigned_count} 个菜单到admin角色")


if __name__ == "__main__":
    asyncio.run(seed())

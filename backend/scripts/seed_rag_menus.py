#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RAG菜单初始化脚本
创建RAG功能菜单并关联到管理员角色
"""
import asyncio
import importlib
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nanoid import generate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from core.menu.model import Menu
from core.role.model import Role


def auto_import_models():
    """自动导入所有model.py文件，避免SQLAlchemy关系解析失败"""
    project_root = Path(__file__).parent.parent
    scan_dirs = ["core", "scheduler", "online_dev", "rag"]
    for scan_dir in scan_dirs:
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


RAG_MENUS = [
    {
        "name": "KnowledgeGraph",
        "title": "知识图谱",
        "path": "/rag",
        "type": "catalog",
        "icon": "Share",
        "order": 55,
        "is_system": True,
        "children": [
            {
                "name": "KnowledgeBaseManager",
                "title": "知识库管理",
                "path": "/rag/knowledge-base",
                "type": "menu",
                "icon": "FolderOpened",
                "component": "/_core/rag/document-view",
                "order": 1,
                "is_system": True,
            },
            {
                "name": "RagQA",
                "title": "知识问答",
                "path": "/rag/qa",
                "type": "menu",
                "icon": "ChatDotSquare",
                "component": "/_core/rag/qa",
                "order": 2,
                "is_system": True,
            },
            {
                "name": "RagGraphView",
                "title": "图谱可视化",
                "path": "/rag/graph/view",
                "type": "menu",
                "icon": "Share",
                "component": "/_core/rag/graph-view",
                "order": 3,
                "is_system": True,
            },
            {
                "name": "RagAiWriter",
                "title": "AI写作",
                "path": "/rag/ai-writer",
                "type": "menu",
                "icon": "Edit",
                "component": "/_core/rag/ai-writer",
                "order": 4,
                "is_system": True,
            },
            {
                "name": "RagFileManager",
                "title": "RAG文件管理",
                "path": "/rag/file-manager",
                "type": "menu",
                "icon": "FolderOpened",
                "component": "/_core/rag/file-manager/index",
                "order": 5,
                "is_system": True,
            },
        ],
    },
]


OLD_CATALOG_NAMES = ["RagPlatform", "KnowledgeGraph"]  # 需要重新创建的目录


async def seed():
    async with AsyncSessionLocal() as db:
        # ========== 清理旧的 RAG 菜单 ==========
        for old_name in OLD_CATALOG_NAMES:
            result = await db.execute(
                select(Menu).where(Menu.name == old_name, Menu.is_deleted == False)
            )
            old_catalog = result.scalar_one_or_none()
            if old_catalog:
                # 获取所有角色
                roles_result = await db.execute(select(Role))
                all_roles = roles_result.scalars().all()

                # 删除子菜单
                children_result = await db.execute(
                    select(Menu).where(Menu.parent_id == old_catalog.id, Menu.is_deleted == False)
                )
                for child in children_result.scalars().all():
                    for role in all_roles:
                        if child in role.menus:
                            role.menus.remove(child)
                    child.is_deleted = True
                    print(f"  删除旧菜单: {child.title}")

                # 从角色关联中移除目录
                for role in all_roles:
                    if old_catalog in role.menus:
                        role.menus.remove(old_catalog)
                old_catalog.is_deleted = True
                print(f"删除旧目录: {old_catalog.title}")
                await db.flush()

        # ========== 创建新菜单 ==========
        result = await db.execute(
            select(Role).where(Role.code == "admin")
        )
        admin_role = result.scalar_one_or_none()
        if not admin_role:
            print("错误: 未找到管理员角色，请先初始化角色数据")
            return

        created_count = 0
        assigned_count = 0

        for catalog_def in RAG_MENUS:
            result = await db.execute(
                select(Menu).where(
                    Menu.name == catalog_def["name"],
                    Menu.is_deleted == False,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                parent_id = existing.id
                # 更新 catalog 的 component 字段（可能在之前版本未设置）
                if catalog_def.get("component"):
                    existing.component = catalog_def["component"]
                print(f"目录已存在: {catalog_def['title']} ({existing.id})")
                if admin_role and existing not in admin_role.menus:
                    admin_role.menus.append(existing)
                    assigned_count += 1
                    print(f"  关联到admin角色: {catalog_def['title']}")
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
                        Menu.is_deleted == False,
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
                        print(f"    关联到admin角色: {child_def['title']}")
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

        # 清除菜单缓存，使新菜单立即生效
        from utils.redis import CacheManager
        menu_cache = CacheManager(prefix="menu:")
        await menu_cache.delete_pattern("tree*")
        await menu_cache.delete_pattern("user_route:*")
        print("已清除菜单Redis缓存")

        print(f"\n完成: 创建 {created_count} 个菜单, 关联 {assigned_count} 个菜单到admin角色")


if __name__ == "__main__":
    asyncio.run(seed())

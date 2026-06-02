#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件管理服务
"""
import mimetypes
import os
from typing import Optional, List, Tuple

from sqlalchemy import select, func, update, case, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.base_service import BaseService
from utils.context import get_current_user_id_from_context
from core.file_manager.model import FileManager
from core.file_manager.schema import FileManagerCreate, FileManagerUpdate
from core.file_manager.storage_backends import get_storage_backend, LocalStorageBackend, MinioStorageBackend


class FileManagerService(BaseService[FileManager, FileManagerCreate, FileManagerUpdate]):
    """文件管理服务"""
    
    model = FileManager

    @classmethod
    async def get_list(
        cls,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        parent_id: Optional[str] = None,
        name: Optional[str] = None,
        type: Optional[str] = None,
        storage_type: Optional[str] = None,
        file_ext: Optional[str] = None,
        is_public: Optional[bool] = None,
        creator_id: Optional[str] = None,
        is_superuser: bool = False,
    ) -> Tuple[List[FileManager], int]:
        """获取文件列表
        
        权限规则：
        - 超管(is_superuser=True)：看到所有文件
        - 普通用户：只看到自己创建的 + 公共的 + 系统文件夹
        """
        # 构建查询条件
        conditions = [cls.model.is_deleted == False]  # noqa: E712
        
        # 父文件夹过滤
        if parent_id is None:
            conditions.append(cls.model.parent_id == None)  # noqa: E711
        else:
            conditions.append(cls.model.parent_id == parent_id)
        
        if name:
            conditions.append(cls.model.name.ilike(f"%{name}%"))
        if type:
            conditions.append(cls.model.type == type)
        if storage_type:
            conditions.append(cls.model.storage_type == storage_type)
        if file_ext:
            conditions.append(cls.model.file_ext == file_ext)
        if is_public is not None:
            conditions.append(cls.model.is_public == is_public)
        
        # 权限过滤：普通用户只看自己的 + 公共的 + 系统文件夹
        if not is_superuser and creator_id:
            conditions.append(
                or_(
                    cls.model.sys_creator_id == creator_id,
                    cls.model.is_public == True,  # noqa: E712
                    cls.model.is_system == True,  # noqa: E712
                )
            )
        
        # 查询总数
        count_query = select(func.count(cls.model.id)).where(*conditions)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 查询数据（文件夹排在前面，新建的排最前）
        offset = (page - 1) * page_size
        type_order = case(
            (cls.model.type == 'folder', 0),
            else_=1
        )
        query = (
            select(cls.model)
            .where(*conditions)
            .order_by(type_order, cls.model.sys_create_datetime.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await db.execute(query)
        items = result.scalars().all()
        
        return items, total

    @classmethod
    async def get_folder_tree(
        cls,
        db: AsyncSession,
        creator_id: Optional[str] = None,
        is_superuser: bool = False,
    ) -> List[FileManager]:
        """获取文件夹树结构
        
        权限规则：
        - 超管：看到所有文件夹
        - 普通用户：只看到自己创建的 + 公共的 + 系统文件夹
        """
        conditions = [
            cls.model.type == 'folder',
            cls.model.is_deleted == False,  # noqa: E712
        ]
        
        if not is_superuser and creator_id:
            conditions.append(
                or_(
                    cls.model.sys_creator_id == creator_id,
                    cls.model.is_public == True,  # noqa: E712
                    cls.model.is_system == True,  # noqa: E712
                )
            )
        
        query = (
            select(cls.model)
            .where(*conditions)
            .order_by(cls.model.name)
        )
        result = await db.execute(query)
        return result.scalars().all()

    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico', '.tiff', '.heic', '.heif'}

    @classmethod
    async def get_recent_images(
        cls,
        db: AsyncSession,
        creator_id: str,
        limit: int = 20,
    ) -> List[FileManager]:
        """获取当前用户最近上传的图片文件（跨所有文件夹，按时间倒序）"""
        query = (
            select(cls.model)
            .where(
                cls.model.type == 'file',
                cls.model.is_deleted == False,  # noqa: E712
                cls.model.file_ext.in_(cls.IMAGE_EXTENSIONS),
                cls.model.sys_creator_id == creator_id,
            )
            .order_by(cls.model.sys_create_datetime.desc())
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def get_recent_files(
        cls,
        db: AsyncSession,
        creator_id: str,
        limit: int = 20,
    ) -> List[FileManager]:
        """获取当前用户最近上传的文件（跨所有文件夹，按时间倒序）"""
        query = (
            select(cls.model)
            .where(
                cls.model.type == 'file',
                cls.model.is_deleted == False,  # noqa: E712
                cls.model.sys_creator_id == creator_id,
            )
            .order_by(cls.model.sys_create_datetime.desc())
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def create_folder(
        cls,
        db: AsyncSession,
        name: str,
        parent_id: Optional[str] = None,
        creator_id: Optional[str] = None,
    ) -> Optional[FileManager]:
        """创建文件夹"""
        if not creator_id:
            creator_id = get_current_user_id_from_context()
        # 获取父文件夹路径
        parent_path = ''
        if parent_id:
            parent = await cls.get_by_id(db, parent_id)
            if parent and parent.type == 'folder':
                parent_path = parent.path
        
        # 构建文件夹路径
        folder_path = os.path.join(parent_path, name).replace('\\', '/') if parent_path else name
        
        # 检查同名文件夹
        existing = await db.execute(
            select(cls.model).where(
                cls.model.parent_id == parent_id,
                cls.model.name == name,
                cls.model.type == 'folder',
                cls.model.is_deleted == False  # noqa: E712
            )
        )
        if existing.scalar_one_or_none():
            return None  # 同名文件夹已存在
        
        # 创建文件夹
        folder = FileManager(
            name=name,
            type='folder',
            parent_id=parent_id,
            path=folder_path,
            storage_path='',
            sys_creator_id=creator_id,
        )
        db.add(folder)
        await db.commit()
        await db.refresh(folder)
        return folder

    # 来源模块 → 系统文件夹名称映射
    SOURCE_LABELS = {
        'announcement': '公告附件',
        'chat': '聊天文件',
        'form': '表单附件',
        'avatar': '头像',
    }

    SYSTEM_ROOT_NAME = 'SystemFile'

    @classmethod
    async def get_or_create_source_folder(
        cls,
        db: AsyncSession,
        source: str,
    ) -> str:
        """根据 source 自动获取或创建 SystemFile/模块文件夹/年-月 三级文件夹，返回日期子文件夹 ID"""
        from datetime import datetime
        folder_name = cls.SOURCE_LABELS.get(source, source)

        # 1. 获取或创建根级 SystemFile 文件夹
        result = await db.execute(
            select(cls.model).where(
                cls.model.parent_id == None,  # noqa: E711
                cls.model.name == cls.SYSTEM_ROOT_NAME,
                cls.model.type == 'folder',
                cls.model.is_system == True,  # noqa: E712
                cls.model.is_deleted == False,  # noqa: E712
            )
        )
        system_root = result.scalar_one_or_none()
        if not system_root:
            system_root = FileManager(
                name=cls.SYSTEM_ROOT_NAME,
                type='folder',
                parent_id=None,
                path=cls.SYSTEM_ROOT_NAME,
                storage_path='',
                is_system=True,
                source='system',
            )
            db.add(system_root)
            await db.flush()

        # 2. 获取或创建模块级文件夹（SystemFile 下）
        module_path = f"{cls.SYSTEM_ROOT_NAME}/{folder_name}"
        result = await db.execute(
            select(cls.model).where(
                cls.model.parent_id == system_root.id,
                cls.model.name == folder_name,
                cls.model.type == 'folder',
                cls.model.is_system == True,  # noqa: E712
                cls.model.is_deleted == False,  # noqa: E712
            )
        )
        module_folder = result.scalar_one_or_none()
        if not module_folder:
            module_folder = FileManager(
                name=folder_name,
                type='folder',
                parent_id=system_root.id,
                path=module_path,
                storage_path='',
                is_system=True,
                source=source,
            )
            db.add(module_folder)
            await db.flush()

        # 3. 获取或创建日期子文件夹（年-月）
        date_name = datetime.now().strftime('%Y-%m')
        date_path = f"{module_path}/{date_name}"

        result = await db.execute(
            select(cls.model).where(
                cls.model.parent_id == module_folder.id,
                cls.model.name == date_name,
                cls.model.type == 'folder',
                cls.model.is_deleted == False,  # noqa: E712
            )
        )
        date_folder = result.scalar_one_or_none()
        if not date_folder:
            date_folder = FileManager(
                name=date_name,
                type='folder',
                parent_id=module_folder.id,
                path=date_path,
                storage_path='',
                is_system=True,
                source=source,
            )
            db.add(date_folder)
            await db.flush()

        return date_folder.id

    @classmethod
    async def upload_file(
        cls,
        db: AsyncSession,
        file_content: bytes,
        filename: str,
        file_size: int,
        parent_id: Optional[str] = None,
        is_public: bool = False,
        creator_id: Optional[str] = None,
        source: Optional[str] = None,
    ) -> FileManager:
        """上传文件"""
        if not creator_id:
            creator_id = get_current_user_id_from_context()
        # 如果有 source 且没有指定 parent_id，自动归入系统文件夹
        if source and not parent_id:
            parent_id = await cls.get_or_create_source_folder(db, source)

        # 获取父文件夹路径
        folder_path = ''
        if parent_id:
            parent = await cls.get_by_id(db, parent_id)
            if parent and parent.type == 'folder':
                folder_path = parent.path
        
        # 获取存储后端
        storage = get_storage_backend()
        
        # 计算文件信息
        file_ext = os.path.splitext(filename)[1].lower()
        mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        # 创建文件对象用于保存
        import io
        file_obj = io.BytesIO(file_content)
        
        # 计算MD5
        md5 = storage.calculate_md5(file_obj)
        file_obj.seek(0)
        
        # 检查是否已存在相同文件（MD5 + 大小双重校验）
        existing = await db.execute(
            select(cls.model).where(
                cls.model.md5 == md5,
                cls.model.size == file_size,
                cls.model.type == 'file',
                cls.model.is_deleted == False,  # noqa: E712
            ).limit(1)
        )
        existing_file = existing.scalar_one_or_none()
        
        if existing_file:
            # 复用已有文件的存储路径，不重复保存
            storage_path = existing_file.storage_path
            url = existing_file.url
            import logging
            logging.getLogger(__name__).info(f"文件 MD5 重复，复用已有存储路径: {storage_path}")
        else:
            # 新文件，保存到存储后端
            storage_path, url = storage.save(file_obj, filename, folder_path)
            import logging
            logging.getLogger(__name__).info(f"新文件保存到: {storage_path}")
        
        # 构建完整路径
        full_path = os.path.join(folder_path, filename).replace('\\', '/') if folder_path else filename
        
        # 创建数据库记录（即使文件内容相同，也创建独立记录，可能在不同文件夹、不同文件名）
        file_record = FileManager(
            name=filename,
            type='file',
            parent_id=parent_id,
            path=full_path,
            size=file_size,
            file_ext=file_ext,
            mime_type=mime_type,
            storage_type=storage.__class__.__name__.replace('StorageBackend', '').lower(),
            storage_path=storage_path,
            url=url,
            md5=md5,
            is_public=is_public,
            source=source,
            sys_creator_id=creator_id,
        )
        db.add(file_record)
        await db.commit()
        await db.refresh(file_record)
        return file_record

    @classmethod
    async def rename_item(
        cls,
        db: AsyncSession,
        item_id: str,
        new_name: str,
        creator_id: Optional[str] = None,
        is_superuser: bool = False,
    ) -> Optional[FileManager]:
        """重命名文件/文件夹
        
        权限规则：普通用户只能重命名自己创建的文件/文件夹
        """
        item = await cls.get_by_id(db, item_id)
        if not item:
            return None
        
        # 系统文件夹不允许重命名
        if item.is_system:
            return None
        
        # 权限校验：普通用户只能操作自己的文件
        if not is_superuser and creator_id and item.sys_creator_id != creator_id:
            return None
        
        # 检查同级目录下是否有同名文件
        existing = await db.execute(
            select(cls.model).where(
                cls.model.parent_id == item.parent_id,
                cls.model.name == new_name,
                cls.model.type == item.type,
                cls.model.id != item_id,
                cls.model.is_deleted == False  # noqa: E712
            )
        )
        if existing.scalar_one_or_none():
            return None  # 同名文件/文件夹已存在
        
        # 更新名称和路径
        old_path = item.path
        if item.parent_id:
            parent = await cls.get_by_id(db, item.parent_id)
            new_path = os.path.join(parent.path, new_name).replace('\\', '/') if parent else new_name
        else:
            new_path = new_name
        
        item.name = new_name
        item.path = new_path
        modifier_id = get_current_user_id_from_context()
        if modifier_id:
            item.sys_modifier_id = modifier_id
        await db.commit()
        await db.refresh(item)
        
        # 如果是文件夹，递归更新子项路径
        if item.type == 'folder':
            await cls._update_children_paths(db, item.id, old_path, new_path)
        
        return item

    @classmethod
    async def move_items(
        cls,
        db: AsyncSession,
        item_ids: List[str],
        target_folder_id: Optional[str] = None,
        creator_id: Optional[str] = None,
        is_superuser: bool = False,
    ) -> bool:
        """移动文件/文件夹
        
        权限规则：普通用户只能移动自己创建的文件/文件夹
        """
        # 获取目标文件夹
        target_path = ''
        if target_folder_id:
            target_folder = await cls.get_by_id(db, target_folder_id)
            if not target_folder or target_folder.type != 'folder':
                return False
            target_path = target_folder.path
        
        for item_id in item_ids:
            item = await cls.get_by_id(db, item_id)
            if not item:
                continue
            
            # 权限校验：普通用户只能操作自己的文件
            if not is_superuser and creator_id and item.sys_creator_id != creator_id:
                continue
            
            # 不能移动到自己或子文件夹
            if item.type == 'folder' and target_folder_id:
                if await cls._is_subfolder(db, target_folder_id, item.id):
                    continue
            
            # 检查目标文件夹是否有同名文件
            existing = await db.execute(
                select(cls.model).where(
                    cls.model.parent_id == target_folder_id,
                    cls.model.name == item.name,
                    cls.model.type == item.type,
                    cls.model.id != item_id,
                    cls.model.is_deleted == False  # noqa: E712
                )
            )
            if existing.scalar_one_or_none():
                continue
            
            # 更新父文件夹和路径
            old_path = item.path
            item.parent_id = target_folder_id
            item.path = os.path.join(target_path, item.name).replace('\\', '/') if target_path else item.name
            modifier_id = get_current_user_id_from_context()
            if modifier_id:
                item.sys_modifier_id = modifier_id
            
            # 如果是文件夹，递归更新子项路径
            if item.type == 'folder':
                await cls._update_children_paths(db, item.id, old_path, item.path)
        
        await db.commit()
        return True

    @classmethod
    async def delete_item(
        cls,
        db: AsyncSession,
        item_id: str,
        hard: bool = False,
        creator_id: Optional[str] = None,
        is_superuser: bool = False,
    ) -> bool:
        """删除文件/文件夹（默认软删除）
        
        权限规则：普通用户只能删除自己创建的文件/文件夹
        """
        item = await cls.get_by_id(db, item_id)
        if not item:
            return False
        
        # 系统文件夹不允许删除
        if item.is_system:
            return False
        
        # 权限校验：普通用户只能操作自己的文件
        if not is_superuser and creator_id and item.sys_creator_id != creator_id:
            return False
        
        # 如果是文件，检查是否有其他记录引用同一存储路径，没有才删除物理文件
        if item.type == 'file' and item.storage_path:
            ref_count = await db.execute(
                select(func.count(cls.model.id)).where(
                    cls.model.storage_path == item.storage_path,
                    cls.model.id != item.id,
                    cls.model.type == 'file',
                    cls.model.is_deleted == False,  # noqa: E712
                )
            )
            if (ref_count.scalar() or 0) == 0:
                storage = get_storage_backend()
                storage.delete(item.storage_path)
        
        # 递归删除子项
        if item.type == 'folder':
            await cls._delete_children(db, item.id, hard)
        
        # 删除数据库记录
        if hard:
            await db.delete(item)
        else:
            item.is_deleted = True
        
        await db.commit()
        return True

    @classmethod
    async def batch_delete(
        cls,
        db: AsyncSession,
        item_ids: List[str],
        hard: bool = False,
        creator_id: Optional[str] = None,
        is_superuser: bool = False,
    ) -> int:
        """批量删除文件/文件夹"""
        deleted_count = 0
        for item_id in item_ids:
            if await cls.delete_item(db, item_id, hard, creator_id=creator_id, is_superuser=is_superuser):
                deleted_count += 1
        return deleted_count

    @classmethod
    async def get_by_storage_path(
        cls,
        db: AsyncSession,
        storage_path: str,
    ) -> Optional[FileManager]:
        """通过存储路径获取文件"""
        result = await db.execute(
            select(cls.model).where(
                cls.model.storage_path == storage_path,
                cls.model.type == 'file',
                cls.model.is_deleted == False  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def increment_download_count(
        cls,
        db: AsyncSession,
        item_id: str,
    ) -> None:
        """增加下载次数"""
        item = await cls.get_by_id(db, item_id)
        if item:
            item.download_count += 1
            await db.commit()

    @classmethod
    async def get_by_md5(
        cls,
        db: AsyncSession,
        md5: str,
        size: int,
    ) -> Optional[FileManager]:
        """通过MD5和大小查找文件（用于秒传）"""
        result = await db.execute(
            select(cls.model).where(
                cls.model.md5 == md5,
                cls.model.size == size,
                cls.model.is_deleted == False  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def has_children(cls, db: AsyncSession, folder_id: str) -> bool:
        """检查文件夹是否有子项"""
        result = await db.execute(
            select(func.count(cls.model.id)).where(
                cls.model.parent_id == folder_id,
                cls.model.is_deleted == False  # noqa: E712
            )
        )
        count = result.scalar() or 0
        return count > 0

    @classmethod
    async def batch_has_children(cls, db: AsyncSession, folder_ids: List[str]) -> dict:
        """批量检查文件夹是否有子项，返回 {folder_id: bool}"""
        if not folder_ids:
            return {}
        result = await db.execute(
            select(
                cls.model.parent_id,
                func.count(cls.model.id).label('cnt')
            ).where(
                cls.model.parent_id.in_(folder_ids),
                cls.model.is_deleted == False  # noqa: E712
            ).group_by(cls.model.parent_id)
        )
        counts = {row[0]: row[1] > 0 for row in result.all()}
        return {fid: counts.get(fid, False) for fid in folder_ids}

    @classmethod
    async def batch_has_sub_folders(cls, db: AsyncSession, folder_ids: List[str]) -> dict:
        """批量检查文件夹是否有子文件夹（不含文件），返回 {folder_id: bool}"""
        if not folder_ids:
            return {}
        result = await db.execute(
            select(
                cls.model.parent_id,
                func.count(cls.model.id).label('cnt')
            ).where(
                cls.model.parent_id.in_(folder_ids),
                cls.model.type == 'folder',
                cls.model.is_deleted == False  # noqa: E712
            ).group_by(cls.model.parent_id)
        )
        counts = {row[0]: row[1] > 0 for row in result.all()}
        return {fid: counts.get(fid, False) for fid in folder_ids}

    @classmethod
    async def batch_get_names(cls, db: AsyncSession, item_ids: List[str]) -> dict:
        """批量获取文件/文件夹名称，返回 {id: name}"""
        if not item_ids:
            return {}
        result = await db.execute(
            select(cls.model.id, cls.model.name).where(
                cls.model.id.in_(item_ids),
                cls.model.is_deleted == False  # noqa: E712
            )
        )
        return {row[0]: row[1] for row in result.all()}

    @classmethod
    async def get_parent(cls, db: AsyncSession, item_id: str) -> Optional[FileManager]:
        """获取父文件夹"""
        item = await cls.get_by_id(db, item_id)
        if item and item.parent_id:
            return await cls.get_by_id(db, item.parent_id)
        return None

    @classmethod
    async def _is_subfolder(cls, db: AsyncSession, folder_id: str, potential_parent_id: str) -> bool:
        """检查folder是否是potential_parent的子文件夹（使用path前缀匹配）"""
        folder = await cls.get_by_id(db, folder_id)
        parent = await cls.get_by_id(db, potential_parent_id)
        if not folder or not parent:
            return False
        # 如果目标文件夹的path以潜在父文件夹的path为前缀，则是子文件夹
        parent_prefix = parent.path + '/'
        return folder.path.startswith(parent_prefix) or folder.id == potential_parent_id

    @classmethod
    async def _update_children_paths(cls, db: AsyncSession, folder_id: str, old_path: str, new_path: str) -> None:
        """批量更新所有后代路径（使用path前缀匹配，一条SQL搞定）"""
        old_prefix = old_path + '/'
        new_prefix = new_path + '/'
        # 使用 LIKE 前缀匹配找到所有后代，批量替换路径前缀
        stmt = (
            update(cls.model)
            .where(
                cls.model.path.like(f"{old_prefix}%"),
                cls.model.is_deleted == False  # noqa: E712
            )
            .values(
                path=func.concat(new_prefix, func.substr(cls.model.path, len(old_prefix) + 1))
            )
        )
        await db.execute(stmt)

    @classmethod
    async def _delete_children(cls, db: AsyncSession, folder_id: str, hard: bool = True) -> None:
        """批量删除所有后代（使用path前缀匹配查找所有后代）"""
        # 先获取当前文件夹的path
        folder = await cls.get_by_id(db, folder_id)
        if not folder:
            return
        
        folder_prefix = folder.path + '/'
        
        # 一次性查出所有后代文件（用于删除存储文件）
        result = await db.execute(
            select(cls.model).where(
                cls.model.path.like(f"{folder_prefix}%"),
                cls.model.type == 'file',
                cls.model.is_deleted == False  # noqa: E712
            )
        )
        file_children = result.scalars().all()
        
        # 删除存储文件
        if file_children:
            storage = get_storage_backend()
            for child in file_children:
                storage.delete(child.storage_path)
        
        # 批量更新/删除所有后代的数据库记录
        if hard:
            from sqlalchemy import delete as sql_delete
            stmt = sql_delete(cls.model).where(
                cls.model.path.like(f"{folder_prefix}%"),
                cls.model.is_deleted == False  # noqa: E712
            )
            await db.execute(stmt)
        else:
            stmt = (
                update(cls.model)
                .where(
                    cls.model.path.like(f"{folder_prefix}%"),
                    cls.model.is_deleted == False  # noqa: E712
                )
                .values(is_deleted=True)
            )
            await db.execute(stmt)

    # 默认最大允许全量读取的文件大小（200MB）
    MAX_FILE_CONTENT_SIZE = 200 * 1024 * 1024

    @classmethod
    async def get_file_content(cls, db: AsyncSession, file_id: str, max_size: int = None) -> Optional[bytes]:
        """
        获取文件内容（字节）
        
        Args:
            db: 数据库会话
            file_id: 文件ID
            max_size: 最大允许读取的文件大小（字节），超过则返回 None，默认200MB
            
        Returns:
            文件内容字节，如果文件不存在或超过大小限制则返回 None
        """
        file_obj = await cls.get_by_id(db, file_id)
        if not file_obj or file_obj.type != 'file':
            return None
        
        # 大文件保护
        limit = max_size or cls.MAX_FILE_CONTENT_SIZE
        if file_obj.size and file_obj.size > limit:
            import logging
            logging.warning(f"File {file_id} ({file_obj.name}) size {file_obj.size} exceeds max_size {limit}, skipping full read")
            return None
        
        storage = get_storage_backend()
        
        try:
            if isinstance(storage, LocalStorageBackend):
                # 本地存储：直接读取文件
                full_path = storage.get_full_path(file_obj.storage_path)
                if os.path.exists(full_path):
                    with open(full_path, 'rb') as f:
                        return f.read()
            elif isinstance(storage, MinioStorageBackend):
                # Minio 存储：通过 API 获取
                response = storage.get_file_content(file_obj.storage_path)
                content = response.read()
                response.close()
                response.release_conn()
                return content
            else:
                # 其他存储后端（OSS、Azure）：通过 URL 下载
                # 这里可以根据需要扩展
                import httpx
                url = file_obj.url
                if url:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            return resp.content
        except Exception as e:
            import logging
            logging.error(f"Failed to get file content for {file_id}: {e}")
        
        return None
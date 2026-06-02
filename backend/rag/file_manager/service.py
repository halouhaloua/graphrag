"""
RAG文件管理服务
"""
import hashlib
import mimetypes
import os
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.base_model import generate_nanoid
from app.config import settings
from rag.file_manager.model import RagFileManager


RAG_FILE_STORAGE_PATH = getattr(
    settings, 'RAG_FILE_STORAGE_PATH',
    os.path.join(os.getcwd(), 'media', 'rag', 'files')
)


def _generate_unique_filename(original_filename: str) -> str:
    """生成唯一文件名，去除路径遍历字符"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    name, ext = os.path.splitext(original_filename)
    safe_name = name.replace("..", "").replace("/", "").replace("\\", "")
    return f"{timestamp}_{safe_name}{ext}"


def _calculate_md5(data: bytes) -> str:
    """计算MD5"""
    return hashlib.md5(data).hexdigest()


def _build_file_response(item: RagFileManager, has_children: bool = False) -> dict:
    """构建文件响应"""
    return {
        "id": item.id,
        "name": item.name,
        "fileType": item.file_type,
        "parentId": item.parent_id,
        "path": item.path,
        "fileSize": item.size,
        "fileExt": item.file_ext,
        "mimeType": item.mime_type,
        "storagePath": item.storage_path,
        "md5": item.md5,
        "scope": item.scope,
        "hasChildren": has_children,
        "updatedTime": item.sys_update_datetime.isoformat() if item.sys_update_datetime else (
            item.sys_create_datetime.isoformat() if item.sys_create_datetime else None
        ),
        "sysCreateDatetime": item.sys_create_datetime,
    }


class RagFileManagerService:

    model = RagFileManager

    @classmethod
    async def get_list(
        cls,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        parent_id: Optional[str] = None,
        scope: Optional[str] = None,
        name: Optional[str] = None,
        file_type: Optional[str] = None,
        creator_id: Optional[str] = None,
    ) -> Tuple[List[RagFileManager], int]:
        """获取文件列表"""
        conditions = [cls.model.is_deleted == False]

        if parent_id is None:
            conditions.append(cls.model.parent_id == None)
        else:
            conditions.append(cls.model.parent_id == parent_id)

        if scope:
            conditions.append(cls.model.scope == scope)

        if name:
            conditions.append(cls.model.name.ilike(f"%{name}%"))

        if file_type:
            conditions.append(cls.model.file_type == file_type)

        if creator_id:
            conditions.append(cls.model.sys_creator_id == creator_id)

        count_query = select(func.count(cls.model.id)).where(*conditions)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = (
            select(cls.model)
            .where(*conditions)
            .order_by(cls.model.file_type, cls.model.sys_create_datetime.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await db.execute(query)
        items = result.scalars().all()

        return items, total

    @classmethod
    async def get_by_id(cls, db: AsyncSession, item_id: str) -> Optional[RagFileManager]:
        result = await db.execute(
            select(cls.model).where(
                cls.model.id == item_id,
                cls.model.is_deleted == False
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def create_folder(
        cls,
        db: AsyncSession,
        name: str,
        scope: str = 'personal',
        parent_id: Optional[str] = None,
        creator_id: Optional[str] = None,
    ) -> Optional[RagFileManager]:
        """创建文件夹"""
        parent_path = ''
        if parent_id:
            parent = await cls.get_by_id(db, parent_id)
            if parent and parent.file_type == 'folder':
                parent_path = parent.path

        folder_path = os.path.join(parent_path, name).replace('\\', '/') if parent_path else name

        existing = await db.execute(
            select(cls.model).where(
                cls.model.parent_id == parent_id,
                cls.model.name == name,
                cls.model.file_type == 'folder',
                cls.model.scope == scope,
                cls.model.is_deleted == False
            )
        )
        if existing.scalar_one_or_none():
            return None

        folder = RagFileManager(
            name=name,
            file_type='folder',
            parent_id=parent_id,
            path=folder_path,
            storage_path='',
            scope=scope,
            sys_creator_id=creator_id,
        )
        db.add(folder)
        await db.commit()
        await db.refresh(folder)
        return folder

    @classmethod
    async def upload_file(
        cls,
        db: AsyncSession,
        file_content: bytes,
        filename: str,
        file_size: int,
        scope: str = 'personal',
        parent_id: Optional[str] = None,
        creator_id: Optional[str] = None,
    ) -> RagFileManager:
        """上传文件"""
        folder_path = ''
        if parent_id:
            parent = await cls.get_by_id(db, parent_id)
            if parent and parent.file_type == 'folder':
                folder_path = parent.path

        unique_filename = _generate_unique_filename(filename)
        relative_path = os.path.join(folder_path, unique_filename).replace('\\', '/')
        if os.path.isabs(relative_path) or ".." in relative_path.split("/"):
            raise ValueError(f"非法文件名: {filename}")
        full_dir = os.path.join(RAG_FILE_STORAGE_PATH, folder_path) if folder_path else RAG_FILE_STORAGE_PATH
        os.makedirs(full_dir, exist_ok=True)
        full_path = os.path.join(RAG_FILE_STORAGE_PATH, relative_path)

        with open(full_path, 'wb') as f:
            f.write(file_content)

        file_ext = os.path.splitext(filename)[1].lower()
        mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        md5 = _calculate_md5(file_content)

        record = RagFileManager(
            name=filename,
            file_type='file',
            parent_id=parent_id,
            path=relative_path,
            size=file_size,
            file_ext=file_ext,
            mime_type=mime_type,
            storage_path=relative_path,
            md5=md5,
            scope=scope,
            sys_creator_id=creator_id,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record

    @classmethod
    async def rename_item(
        cls,
        db: AsyncSession,
        item_id: str,
        new_name: str,
    ) -> Optional[RagFileManager]:
        item = await cls.get_by_id(db, item_id)
        if not item:
            return None

        existing = await db.execute(
            select(cls.model).where(
                cls.model.parent_id == item.parent_id,
                cls.model.name == new_name,
                cls.model.file_type == item.file_type,
                cls.model.id != item_id,
                cls.model.is_deleted == False
            )
        )
        if existing.scalar_one_or_none():
            return None

        old_path = item.path
        if item.parent_id:
            parent = await cls.get_by_id(db, item.parent_id)
            new_path = os.path.join(parent.path, new_name).replace('\\', '/') if parent else new_name
        else:
            new_path = new_name

        item.name = new_name
        item.path = new_path
        await db.commit()
        await db.refresh(item)

        if item.file_type == 'folder':
            await cls._update_children_paths(db, item.id, old_path, new_path)

        return item

    @classmethod
    async def delete_item(
        cls,
        db: AsyncSession,
        item_id: str,
        hard: bool = True,
    ) -> bool:
        item = await cls.get_by_id(db, item_id)
        if not item:
            return False

        if item.file_type == 'file':
            full_path = os.path.join(RAG_FILE_STORAGE_PATH, item.storage_path)
            if os.path.exists(full_path):
                os.remove(full_path)

        if item.file_type == 'folder':
            await cls._delete_children(db, item.id, hard)

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
        hard: bool = True,
    ) -> int:
        deleted_count = 0
        for item_id in item_ids:
            if await cls.delete_item(db, item_id, hard):
                deleted_count += 1
        return deleted_count

    @classmethod
    async def get_text_content(cls, db: AsyncSession, file_id: str) -> Optional[dict]:
        """获取文件的文本内容和识别状态"""
        item = await cls.get_by_id(db, file_id)
        if not item or item.file_type != 'file':
            return None
        return {
            "text_content": item.text_content,
            "ocr_status": item.ocr_status or 'none',
            "llm_status": item.llm_status or 'none',
        }

    @classmethod
    async def update_text_content(
        cls, db: AsyncSession, file_id: str, text_content: str
    ) -> Optional[RagFileManager]:
        """更新文件文本内容"""
        item = await cls.get_by_id(db, file_id)
        if not item or item.file_type != 'file':
            return None
        item.text_content = text_content
        await db.commit()
        await db.refresh(item)
        return item

    @classmethod
    async def add_to_knowledge_base(
        cls, db: AsyncSession, file_id: str, kb_id: str, creator_id: Optional[str] = None
    ) -> Optional[dict]:
        """将文件文本内容添加到指定知识库"""
        from rag.kb_manager.model import KnowledgeBaseFile as KBFileModel

        item = await cls.get_by_id(db, file_id)
        if not item or item.file_type != 'file':
            return None
        text = item.text_content or ''
        new_id = generate_nanoid()
        file_ext = item.file_ext or ''
        record = KBFileModel(
            id=new_id,
            kb_id=kb_id,
            filename=item.name,
            content=text,
            file_type=file_ext if file_ext else '.txt',
            file_size=item.size or 0,
            has_graph=False,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return {
            "id": record.id,
            "kb_id": record.kb_id,
            "filename": record.filename,
        }

    @classmethod
    async def has_children(cls, db: AsyncSession, folder_id: str) -> bool:
        result = await db.execute(
            select(func.count(cls.model.id)).where(
                cls.model.parent_id == folder_id,
                cls.model.is_deleted == False
            )
        )
        count = result.scalar() or 0
        return count > 0

    @classmethod
    async def _update_children_paths(cls, db: AsyncSession, folder_id: str, old_path: str, new_path: str) -> None:
        result = await db.execute(
            select(cls.model).where(
                cls.model.parent_id == folder_id,
                cls.model.is_deleted == False
            )
        )
        children = result.scalars().all()
        for child in children:
            child.path = child.path.replace(old_path, new_path, 1)
            if child.file_type == 'folder':
                await cls._update_children_paths(db, child.id, old_path, new_path)

    @classmethod
    async def _delete_children(cls, db: AsyncSession, folder_id: str, hard: bool = True) -> None:
        result = await db.execute(
            select(cls.model).where(
                cls.model.parent_id == folder_id,
                cls.model.is_deleted == False
            )
        )
        children = result.scalars().all()
        for child in children:
            if child.file_type == 'file':
                full_path = os.path.join(RAG_FILE_STORAGE_PATH, child.storage_path)
                if os.path.exists(full_path):
                    os.remove(full_path)
            if child.file_type == 'folder':
                await cls._delete_children(db, child.id, hard)
            if hard:
                await db.delete(child)
            else:
                child.is_deleted = True

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """清理文本中PostgreSQL无法存储的非法字符"""
        return text.replace('\x00', '')

    @classmethod
    async def trigger_ocr(cls, db: AsyncSession, file_id: str) -> Optional[dict]:
        """触发传统OCR识别（PyPDF2/pdfplumber/docx）"""
        from rag.file_manager.ocr import common_ocr

        item = await cls.get_by_id(db, file_id)
        if not item or item.file_type != 'file':
            return None

        item.ocr_status = 'pending'
        await db.commit()

        try:
            full_path = os.path.join(RAG_FILE_STORAGE_PATH, item.storage_path)
            text = cls._sanitize_text(await common_ocr(full_path, item.file_ext or ''))
            item.text_content = text
            item.ocr_status = 'completed'
        except Exception:
            item.ocr_status = 'failed'

        await db.commit()
        await db.refresh(item)
        return {"textContent": item.text_content, "ocrStatus": item.ocr_status}

    @classmethod
    async def trigger_complex_ocr(cls, db: AsyncSession, file_id: str) -> Optional[dict]:
        """触发复杂竖排繁体文本OCR（PP-OCRv5）"""
        from rag.file_manager.ocr import complex_ocr

        item = await cls.get_by_id(db, file_id)
        if not item or item.file_type != 'file':
            return None

        item.llm_status = 'pending'
        await db.commit()

        try:
            full_path = os.path.join(RAG_FILE_STORAGE_PATH, item.storage_path)
            text = cls._sanitize_text(await complex_ocr(full_path, item.file_ext or ''))
            item.text_content = text
            item.llm_status = 'completed'
        except Exception:
            item.llm_status = 'failed'

        await db.commit()
        await db.refresh(item)
        return {"textContent": item.text_content, "llmStatus": item.llm_status}

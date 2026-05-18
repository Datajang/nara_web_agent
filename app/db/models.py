from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    email         = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow)
    projects      = relationship("Project", back_populates="user", cascade="all, delete")

class Project(Base):
    __tablename__ = "projects"
    id                 = Column(Integer, primary_key=True, autoincrement=True)
    user_id            = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name               = Column(String, nullable=False)
    department_profile = Column(Text)
    created_at         = Column(DateTime, default=datetime.utcnow)
    user               = relationship("User", back_populates="projects")
    conversations      = relationship("Conversation", back_populates="project", cascade="all, delete")
    bookmarks          = relationship("BookmarkedBid", back_populates="project", cascade="all, delete")

class Conversation(Base):
    __tablename__ = "conversations"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title      = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    project    = relationship("Project", back_populates="conversations")
    messages   = relationship("Message", back_populates="conversation", cascade="all, delete")

class Message(Base):
    __tablename__ = "messages"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role            = Column(String, nullable=False)
    content         = Column(Text, nullable=False)
    step            = Column(String)
    metadata_       = Column("metadata", Text)
    created_at      = Column(DateTime, default=datetime.utcnow)
    conversation    = relationship("Conversation", back_populates="messages")

class BookmarkedBid(Base):
    __tablename__ = "bookmarked_bids"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    project_id       = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    bid_title        = Column(String, nullable=False)
    bid_number       = Column(String)
    file_url         = Column(String)
    analysis_summary = Column(Text)
    bookmarked_at    = Column(DateTime, default=datetime.utcnow)
    project          = relationship("Project", back_populates="bookmarks")

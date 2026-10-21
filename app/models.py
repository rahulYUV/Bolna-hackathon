from pydantic import BaseModel
from typing import List

class GroupCreate(BaseModel):
    name: str

class GroupMemberAdd(BaseModel):
    customer_id: int

class ExpenseSplit(BaseModel):
    customer_id: int
    amount_owed: float

class ExpenseCreate(BaseModel):
    group_id: int
    description: str
    amount: float
    paid_by: int
    splits: List[ExpenseSplit]
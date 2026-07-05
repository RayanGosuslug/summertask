from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
import uuid
import json

app = FastAPI(title="Apex Karting BFF", version="1.0")

# -------------------- Модели данных (DTO) --------------------
class TrackConfiguration(BaseModel):
    id: str
    name: str
    description: str
    difficulty: str  # "novice" или "advanced"

class Marshal(BaseModel):
    id: str
    fullName: str
    photoUrl: Optional[str] = None

class Slot(BaseModel):
    id: str
    startTime: datetime
    endTime: datetime
    trackConfiguration: TrackConfiguration
    marshal: Marshal
    totalKarts: int
    availableKarts: int
    maxParticipantsForNovice: Optional[int] = None
    rentalEquipmentAvailable: int
    status: str  # "available", "fully_booked", "cancelled_by_center"
    cancellationReason: Optional[str] = None
    address: str
    meetingPoint: str

class Booking(BaseModel):
    id: str
    slotId: str
    userId: str
    participantsCount: int
    needRentalEquipment: bool
    rentalEquipmentProvided: bool = False
    status: str  # "confirmed", "cancelled_by_client", "cancelled_by_center"
    cancellationReason: Optional[str] = None
    createdAt: datetime
    clientComment: Optional[str] = None

class BookingCreate(BaseModel):
    slotId: str
    participantsCount: int = Field(..., ge=1)
    needRentalEquipment: bool = False
    clientComment: Optional[str] = None

class RatingCreate(BaseModel):
    bookingId: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

class UserProfile(BaseModel):
    id: str
    phoneNumber: str
    fullName: str
    isRegular: bool
    regularityBadge: Optional[str] = None
    totalRides: int

# -------------------- Имитация существующего бэкенда (in-memory) --------------------
class InternalBackend:
    def __init__(self):
        self.tracks = {
            "track1": TrackConfiguration(
                id="track1",
                name="Короткая трасса",
                description="Для новичков, 600 м, 6 поворотов",
                difficulty="novice"
            ),
            "track2": TrackConfiguration(
                id="track2",
                name="Длинная трасса",
                description="Для опытных, 1200 м, 12 поворотов",
                difficulty="advanced"
            )
        }
        self.marshals = {
            "marshal1": Marshal(id="marshal1", fullName="Алексей Смирнов", photoUrl=None),
            "marshal2": Marshal(id="marshal2", fullName="Елена Кузнецова", photoUrl=None),
        }
        self.slots = {}
        self.bookings = {}
        self.ratings = []
        self.users = {
            "user1": UserProfile(
                id="user1",
                phoneNumber="+79991234567",
                fullName="Иван Петров",
                isRegular=True,
                regularityBadge="Золотой карт",
                totalRides=42
            )
        }
        self._generate_slots()

    def _generate_slots(self):
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        start = now + timedelta(hours=2)
        for day in range(7):
            day_start = start + timedelta(days=day)
            for hour in [10, 12, 14, 16, 18]:
                slot_start = day_start.replace(hour=hour)
                if slot_start < now:
                    continue
                slot_id = str(uuid.uuid4())
                track = self.tracks["track1"] if day % 2 == 0 else self.tracks["track2"]
                marshal = self.marshals["marshal1"] if hour % 2 == 0 else self.marshals["marshal2"]
                total = 14
                max_novice = 8 if track.difficulty == "novice" else None
                available = min(total, max_novice) if max_novice else total
                if day == 0 and hour == 10:
                    available = 1
                self.slots[slot_id] = Slot(
                    id=slot_id,
                    startTime=slot_start,
                    endTime=slot_start + timedelta(minutes=20),
                    trackConfiguration=track,
                    marshal=marshal,
                    totalKarts=total,
                    availableKarts=available,
                    maxParticipantsForNovice=max_novice,
                    rentalEquipmentAvailable=5,
                    status="available",
                    cancellationReason=None,
                    address="ул. Трассовая, д. 1",
                    meetingPoint="Сбор у стойки регистрации за 15 минут до старта"
                )

    # ---------- ИСПРАВЛЕННЫЙ МЕТОД: фильтруем прошедшие слоты ----------
    def get_slots(self, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None):
        if from_date is None:
            from_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if to_date is None:
            to_date = from_date + timedelta(days=7)
        now = datetime.now()
        result = []
        for slot in self.slots.values():
            # Показываем только будущие слоты (>= текущего момента)
            if slot.startTime >= now and from_date <= slot.startTime < to_date:
                result.append(slot)
        return sorted(result, key=lambda s: s.startTime)

    def get_slot(self, slot_id: str):
        return self.slots.get(slot_id)

    # ---------- ИСПРАВЛЕННЫЙ МЕТОД: проверка дублирования брони ----------
    def create_booking(self, user_id: str, slot_id: str, participants: int, need_rental: bool, comment: str = None):
        # Проверка: нет ли уже активной брони у пользователя на этот слот
        for booking in self.bookings.values():
            if booking.userId == user_id and booking.slotId == slot_id and booking.status == "confirmed":
                raise ValueError("User already has a booking for this slot")

        slot = self.slots.get(slot_id)
        if not slot:
            raise ValueError("Slot not found")
        if slot.status != "available":
            raise ValueError("Slot is not available")
        if slot.availableKarts < participants:
            raise ValueError("Not enough karts available")
        if need_rental and slot.rentalEquipmentAvailable < participants:
            raise ValueError("Not enough rental equipment")

        # Атомарное уменьшение
        slot.availableKarts -= participants
        if need_rental:
            slot.rentalEquipmentAvailable -= participants

        booking_id = str(uuid.uuid4())
        booking = Booking(
            id=booking_id,
            slotId=slot_id,
            userId=user_id,
            participantsCount=participants,
            needRentalEquipment=need_rental,
            rentalEquipmentProvided=False,
            status="confirmed",
            cancellationReason=None,
            createdAt=datetime.now(),
            clientComment=comment
        )
        self.bookings[booking_id] = booking

        if slot.availableKarts == 0:
            slot.status = "fully_booked"
        return booking

    # ---------- ИСПРАВЛЕННЫЙ МЕТОД: запрет отмены после старта и <10 мин ----------
    def cancel_booking(self, booking_id: str, user_id: str):
        booking = self.bookings.get(booking_id)
        if not booking:
            raise ValueError("Booking not found")
        if booking.userId != user_id:
            raise ValueError("Not your booking")
        if booking.status != "confirmed":
            raise ValueError("Booking already cancelled")

        slot = self.slots.get(booking.slotId)
        if not slot:
            raise ValueError("Slot not found")

        now = datetime.now()
        # Запрещаем отмену, если заезд уже начался или прошёл
        if slot.startTime <= now:
            raise ValueError("Cannot cancel after start")
        # Запрещаем отмену менее чем за 10 минут до старта
        if (slot.startTime - now).total_seconds() < 10 * 60:
            raise ValueError("Cannot cancel less than 10 minutes before start")

        # Возвращаем места
        slot.availableKarts += booking.participantsCount
        if booking.needRentalEquipment:
            slot.rentalEquipmentAvailable += booking.participantsCount
        if slot.status == "fully_booked" and slot.availableKarts > 0:
            slot.status = "available"

        booking.status = "cancelled_by_client"
        return booking

    def add_rating(self, user_id: str, booking_id: str, rating: int, comment: str = None):
        booking = self.bookings.get(booking_id)
        if not booking:
            raise ValueError("Booking not found")
        if booking.userId != user_id:
            raise ValueError("Not your booking")

        slot = self.slots.get(booking.slotId)
        if not slot or slot.startTime > datetime.now():
            raise ValueError("Cannot rate before the ride")

        self.ratings.append({
            "bookingId": booking_id,
            "userId": user_id,
            "rating": rating,
            "comment": comment,
            "createdAt": datetime.now()
        })
        return {"status": "ok"}

    def get_user_profile(self, user_id: str):
        return self.users.get(user_id)

backend = InternalBackend()

# -------------------- Зависимости для аутентификации (заглушка) --------------------
def get_current_user(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = authorization.split(" ")[1]
    if user_id not in backend.users:
        raise HTTPException(status_code=401, detail="User not found")
    return user_id

# -------------------- Эндпоинты BFF --------------------

@app.get("/slots", response_model=List[Slot])
async def get_slots(from_date: Optional[str] = None, to_date: Optional[str] = None):
    f_date = None
    t_date = None
    if from_date:
        try:
            f_date = datetime.fromisoformat(from_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from_date format, use YYYY-MM-DD")
    if to_date:
        try:
            t_date = datetime.fromisoformat(to_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_date format, use YYYY-MM-DD")
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if f_date is None:
        f_date = now
    if t_date is None:
        t_date = f_date + timedelta(days=7)
    slots = backend.get_slots(f_date, t_date)
    return slots

@app.get("/slots/{slot_id}", response_model=Slot)
async def get_slot(slot_id: str):
    slot = backend.get_slot(slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    return slot

@app.post("/bookings", response_model=Booking)
async def create_booking(booking_data: BookingCreate, user_id: str = Depends(get_current_user)):
    try:
        booking = backend.create_booking(
            user_id=user_id,
            slot_id=booking_data.slotId,
            participants=booking_data.participantsCount,
            need_rental=booking_data.needRentalEquipment,
            comment=booking_data.clientComment
        )
        return booking
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@app.delete("/bookings/{booking_id}", response_model=Booking)
async def cancel_booking(booking_id: str, user_id: str = Depends(get_current_user)):
    try:
        booking = backend.cancel_booking(booking_id, user_id)
        return booking
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/ratings")
async def add_rating(rating_data: RatingCreate, user_id: str = Depends(get_current_user)):
    try:
        backend.add_rating(user_id, rating_data.bookingId, rating_data.rating, rating_data.comment)
        return {"message": "Rating submitted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/profile", response_model=UserProfile)
async def get_profile(user_id: str = Depends(get_current_user)):
    profile = backend.get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
# test_api.py
import pytest
from fastapi.testclient import TestClient
from maincorr import app, backend, Slot
from datetime import datetime, timedelta
import uuid

client = TestClient(app)

# Фикстура для авторизации (заглушка)
def auth_headers(user_id="user1"):
    return {"Authorization": f"Bearer {user_id}"}

# Фикстура для создания тестового слота (чтобы не зависеть от сгенерированных)
@pytest.fixture
def test_slot():
    # Создаём слот в памяти с явным временем в будущем (через 2 часа)
    slot_id = str(uuid.uuid4())
    now = datetime.now()
    start = now + timedelta(hours=2)
    end = start + timedelta(minutes=20)
    track = backend.tracks["track1"]
    marshal = backend.marshals["marshal1"]
    slot = Slot(
        id=slot_id,
        startTime=start,
        endTime=end,
        trackConfiguration=track,
        marshal=marshal,
        totalKarts=14,
        availableKarts=5,
        maxParticipantsForNovice=8,
        rentalEquipmentAvailable=3,
        status="available",
        cancellationReason=None,
        address="ул. Трассовая, д. 1",
        meetingPoint="Сбор у стойки регистрации за 15 минут до старта"
    )
    backend.slots[slot_id] = slot
    yield slot_id
    # Чистка
    del backend.slots[slot_id]

@pytest.fixture
def test_booking(test_slot):
    # Создаём бронь
    user_id = "user1"
    slot_id = test_slot
    # Убедимся, что слот доступен
    slot = backend.slots[slot_id]
    slot.availableKarts = 5  # сбросим
    slot.rentalEquipmentAvailable = 3
    booking = backend.create_booking(user_id, slot_id, 2, False)
    yield booking.id
    # Чистка
    if booking.id in backend.bookings:
        del backend.bookings[booking.id]
    # Возвращаем места (если не отменено)
    slot.availableKarts += 2

# Тесты

def test_get_slots_default():
    response = client.get("/slots")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Проверяем, что все слоты в будущем (не раньше текущего времени минус погрешность)
    now = datetime.now()
    for slot in data:
        start = datetime.fromisoformat(slot["startTime"].replace('Z', '+00:00'))
        assert start >= now - timedelta(minutes=1)  # допустим, что слоты могут быть через пару минут

def test_get_slots_filter():
    # Берем диапазон на 2 дня вперед
    from_date = (datetime.now() + timedelta(days=1)).date().isoformat()
    to_date = (datetime.now() + timedelta(days=3)).date().isoformat()
    response = client.get(f"/slots?from={from_date}&to={to_date}")
    assert response.status_code == 200
    data = response.json()
    for slot in data:
        start = datetime.fromisoformat(slot["startTime"].replace('Z', '+00:00'))
        assert start.date() >= datetime.fromisoformat(from_date).date()
        assert start.date() < datetime.fromisoformat(to_date).date()

def test_get_slot_detail(test_slot):
    response = client.get(f"/slots/{test_slot}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_slot
    assert "trackConfiguration" in data
    assert "marshal" in data

def test_get_slot_not_found():
    response = client.get("/slots/non-existent-id")
    assert response.status_code == 404

def test_create_booking_success(test_slot):
    payload = {
        "slotId": test_slot,
        "participantsCount": 2,
        "needRentalEquipment": True,
        "clientComment": "test"
    }
    response = client.post("/bookings", json=payload, headers=auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["slotId"] == test_slot
    assert data["status"] == "confirmed"
    # Проверяем уменьшение мест
    slot = backend.slots[test_slot]
    assert slot.availableKarts == 3  # было 5, заняли 2
    assert slot.rentalEquipmentAvailable == 1  # было 3, заняли 2
    # Очистим бронь для следующих тестов
    backend.bookings.pop(data["id"])
    slot.availableKarts += 2
    slot.rentalEquipmentAvailable += 2

def test_create_booking_no_karts(test_slot):
    # Делаем слот полностью занятым
    slot = backend.slots[test_slot]
    slot.availableKarts = 0
    payload = {
        "slotId": test_slot,
        "participantsCount": 1,
        "needRentalEquipment": False
    }
    response = client.post("/bookings", json=payload, headers=auth_headers())
    assert response.status_code == 409
    assert "Not enough karts" in response.text
    # Восстанавливаем
    slot.availableKarts = 5

def test_create_booking_no_equipment(test_slot):
    # Делаем оборудование недоступным
    slot = backend.slots[test_slot]
    slot.rentalEquipmentAvailable = 0
    payload = {
        "slotId": test_slot,
        "participantsCount": 1,
        "needRentalEquipment": True
    }
    response = client.post("/bookings", json=payload, headers=auth_headers())
    assert response.status_code == 409
    assert "Not enough rental equipment" in response.text
    slot.rentalEquipmentAvailable = 3

def test_create_booking_duplicate(test_slot):
    # Сначала записываемся
    payload = {
        "slotId": test_slot,
        "participantsCount": 1,
        "needRentalEquipment": False
    }
    response1 = client.post("/bookings", json=payload, headers=auth_headers())
    assert response1.status_code == 200
    booking_id = response1.json()["id"]
    # Пытаемся записаться снова
    response2 = client.post("/bookings", json=payload, headers=auth_headers())
    assert response2.status_code == 409  # или 400, ожидаем ошибку
    # Очистка
    slot = backend.slots[test_slot]
    slot.availableKarts += 1
    backend.bookings.pop(booking_id)

def test_cancel_booking_before_10min(test_booking):
    booking_id = test_booking
    # Убедимся, что до старта больше 10 минут. В тестовом слоте старт через 2 часа, так что ок.
    response = client.delete(f"/bookings/{booking_id}", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled_by_client"
    # Проверяем возврат мест
    slot_id = data["slotId"]
    slot = backend.slots[slot_id]
    # Количество мест должно быть восстановлено (изначально было 5, заняли 2, после отмены стало 5)
    # В тестовом бронировании мы создавали с 2 участниками, поэтому после отмены должно быть 5
    assert slot.availableKarts == 5

def test_cancel_booking_less_than_10min(test_slot):
    # Создаём слот с началом через 5 минут
    now = datetime.now()
    start = now + timedelta(minutes=5)
    slot_id = str(uuid.uuid4())
    track = backend.tracks["track1"]
    marshal = backend.marshals["marshal1"]
    slot = Slot(
        id=slot_id,
        startTime=start,
        endTime=start + timedelta(minutes=20),
        trackConfiguration=track,
        marshal=marshal,
        totalKarts=14,
        availableKarts=5,
        maxParticipantsForNovice=8,
        rentalEquipmentAvailable=3,
        status="available",
        cancellationReason=None,
        address="ул. Трассовая, д. 1",
        meetingPoint="Сбор у стойки регистрации за 15 минут до старта"
    )
    backend.slots[slot_id] = slot
    # Создаём бронь
    booking = backend.create_booking("user1", slot_id, 1, False)
    # Пытаемся отменить
    response = client.delete(f"/bookings/{booking.id}", headers=auth_headers())
    assert response.status_code == 400
    assert "Cannot cancel less than 10 minutes" in response.text
    # Чистка
    del backend.slots[slot_id]
    del backend.bookings[booking.id]

def test_cancel_booking_after_start(test_slot):
    # Создаём слот с началом в прошлом (5 минут назад)
    now = datetime.now()
    start = now - timedelta(minutes=5)
    slot_id = str(uuid.uuid4())
    track = backend.tracks["track1"]
    marshal = backend.marshals["marshal1"]
    slot = Slot(
        id=slot_id,
        startTime=start,
        endTime=start + timedelta(minutes=20),
        trackConfiguration=track,
        marshal=marshal,
        totalKarts=14,
        availableKarts=5,
        maxParticipantsForNovice=8,
        rentalEquipmentAvailable=3,
        status="available",
        cancellationReason=None,
        address="ул. Трассовая, д. 1",
        meetingPoint="Сбор у стойки регистрации за 15 минут до старта"
    )
    backend.slots[slot_id] = slot
    booking = backend.create_booking("user1", slot_id, 1, False)
    response = client.delete(f"/bookings/{booking.id}", headers=auth_headers())
    assert response.status_code == 400
    assert "Cannot cancel after start" in response.text
    del backend.slots[slot_id]
    del backend.bookings[booking.id]

def test_rating_after_ride(test_booking):
    # Для теста изменим время начала слота на прошлое
    booking = backend.bookings[test_booking]
    slot = backend.slots[booking.slotId]
    original_start = slot.startTime
    slot.startTime = datetime.now() - timedelta(hours=1)  # уже прошёл
    # Отправляем оценку
    payload = {
        "bookingId": test_booking,
        "rating": 5,
        "comment": "Great!"
    }
    response = client.post("/ratings", json=payload, headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["message"] == "Rating submitted"
    # Восстанавливаем
    slot.startTime = original_start

def test_rating_before_ride(test_slot):
    # Создаём бронь на будущий слот
    booking = backend.create_booking("user1", test_slot, 1, False)
    payload = {
        "bookingId": booking.id,
        "rating": 5
    }
    response = client.post("/ratings", json=payload, headers=auth_headers())
    assert response.status_code == 400
    assert "Cannot rate before the ride" in response.text
    # Чистка
    del backend.bookings[booking.id]
    slot = backend.slots[test_slot]
    slot.availableKarts += 1

def test_profile():
    response = client.get("/profile", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "user1"
    assert data["isRegular"] == True
1. Тест-кейсы для MVP (основные сценарии)

Ниже приведены ключевые тест-кейсы для проверки API BFF. Они покрывают функциональность просмотра, бронирования, отмены и оценки.
ID	Название	Предусловия	Шаги	Ожидаемый результат
TC-01	Получение списка слотов по умолчанию	Нет	GET /slots без параметров	Возвращается список слотов на ближайшие 7 дней (включая текущий день), только будущие заезды
TC-02	Получение списка слотов с фильтром дат	Нет	GET /slots?from=2026-07-10&to=2026-07-12	Возвращаются слоты только в указанном диапазоне
TC-03	Получение деталей существующего слота	Слот с id=slot1 существует	GET /slots/slot1	Возвращается полная информация о слоте
TC-04	Получение деталей несуществующего слота	Нет	GET /slots/несуществующий_id	Ошибка 404 Not Found
TC-05	Успешное бронирование	Слот имеет свободные места, оборудование есть	POST /bookings с валидными данными	Возвращается подтверждение, количество свободных мест уменьшено
TC-06	Бронирование при недостатке картов	Слот имеет 0 свободных картов	POST /bookings с participantsCount=1	Ошибка 409 Conflict с сообщением о нехватке мест
TC-07	Бронирование при недостатке прокатного оборудования	Слот имеет 0 прокатных комплектов, но карты есть	POST /bookings с needRentalEquipment=true	Ошибка 409 Conflict
TC-08	Повторное бронирование одного пользователя на тот же слот	Пользователь уже записан на этот слот	POST /bookings на тот же слот	Ошибка 409 (или 400) о том, что уже записан
TC-09	Отмена бронирования до старта (более 10 минут)	Бронь существует, до старта >10 мин	DELETE /bookings/{id}	Бронь отменена, места возвращены, статус cancelled_by_client
TC-10	Отмена бронирования менее чем за 10 минут до старта	Бронь существует, до старта 5 мин	DELETE /bookings/{id}	Ошибка 400 о невозможности отмены
TC-11	Отмена бронирования после старта	Бронь существует, заезд уже начался	DELETE /bookings/{id}	Ошибка 400 о невозможности отмены после старта
TC-12	Оценка маршала после заезда	Заезд завершён, бронь у пользователя	POST /ratings с валидными данными	Оценка сохранена, ответ 200
TC-13	Оценка маршала до начала заезда	Заезд ещё не начался	POST /ratings	Ошибка 400 о том, что нельзя оценить до заезда
TC-14	Получение профиля пользователя	Пользователь авторизован	GET /profile
3. Обнаруженные баги и их исправления

Баг №1: В список слотов попадают прошедшие заезды

Описание: В get_slots мы не фильтруем слоты, которые уже начались, поэтому клиент видит неактуальные записи.
Исправление: Добавить условие slot.startTime >= datetime.now() при фильтрации.

Изменение в main.py (функция get_slots):
python

def get_slots(self, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None):
    if from_date is None:
        from_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if to_date is None:
        to_date = from_date + timedelta(days=7)
    now = datetime.now()
    result = []
    for slot in self.slots.values():
        if slot.startTime >= now and from_date <= slot.startTime < to_date:
            result.append(slot)
    return sorted(result, key=lambda s: s.startTime)

Баг №2: Разрешена отмена бронирования после старта заезда

Описание: В cancel_booking условие проверки времени (slot.startTime - now).total_seconds() < 10 * 60 становится истинным, если startTime уже прошёл (отрицательная разница), что позволяет отменить бронь после старта.
Исправление: Добавить проверку, что слот ещё не начался.

Изменение в main.py (функция cancel_booking):
python

def cancel_booking(self, booking_id: str, user_id: str):
    ...
    now = datetime.now()
    if slot.startTime <= now:
        raise ValueError("Cannot cancel after start")
    if (slot.startTime - now).total_seconds() < 10 * 60:
        raise ValueError("Cannot cancel less than 10 minutes before start")
    ...

Баг №3: Пользователь может записаться на один и тот же слот несколько раз

Описание: При создании бронирования мы не проверяем, есть ли уже активная бронь у этого пользователя на данный слот, что приводит к дублированию.
Исправление: Добавить проверку в create_booking, что пользователь не имеет подтверждённой брони на этот слот.

Изменение в main.py (функция create_booking):
python

def create_booking(self, user_id: str, slot_id: str, participants: int, need_rental: bool, comment: str = None):
    # Проверка на дублирование
    for booking in self.bookings.values():
        if booking.userId == user_id and booking.slotId == slot_id and booking.status == "confirmed":
            raise ValueError("User already has a booking for this slot")
    ...

4. Исправленный код BFF (основные изменения)

Все изменения внесены в класс InternalBackend. Полный исправленный код можно получить, заменив методы в исходном файле main.py на приведённые выше.

После исправлений все тесты должны проходить успешно.
5. Итоговый скрипт для проверки (запуск тестов)

Сохраните test_api.py и выполните:
bash

pytest test_api.py -v --tb=short

Если сервер не запущен, можно использовать TestClient без отдельного запуска (как в коде выше), так как мы импортируем app напрямую. Тесты будут запускаться в том же процессе.

================================================== test session starts ===================================================
platform win32 -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Zalman\AppData\Local\Programs\Python\Python313\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\Zalman\Downloads
plugins: anyio-4.14.1
collected 14 items                                                                                                        

test_api.py::test_get_slots_default PASSED                                                                          [  7%]
test_api.py::test_get_slots_filter FAILED                                                                           [ 14%]
test_api.py::test_get_slot_detail PASSED                                                                            [ 21%]
test_api.py::test_get_slot_not_found PASSED                                                                         [ 28%]
test_api.py::test_create_booking_success PASSED                                                                     [ 35%]
test_api.py::test_create_booking_no_karts PASSED                                                                    [ 42%]
test_api.py::test_create_booking_no_equipment PASSED                                                                [ 50%]
test_api.py::test_create_booking_duplicate FAILED                                                                   [ 57%]
test_api.py::test_cancel_booking_before_10min PASSED                                                                [ 64%]
test_api.py::test_cancel_booking_less_than_10min PASSED                                                             [ 71%]
test_api.py::test_cancel_booking_after_start FAILED                                                                 [ 78%]
test_api.py::test_rating_after_ride PASSED                                                                          [ 85%]
test_api.py::test_rating_before_ride PASSED                                                                         [ 92%]
test_api.py::test_profile PASSED                                                                                    [100%]

======================================================== FAILURES ========================================================
_________________________________________________ test_get_slots_filter __________________________________________________

    def test_get_slots_filter():
        # Берем диапазон на 2 дня вперед
        from_date = (datetime.now() + timedelta(days=1)).date().isoformat()
        to_date = (datetime.now() + timedelta(days=3)).date().isoformat()
        response = client.get(f"/slots?from={from_date}&to={to_date}")
        assert response.status_code == 200
        data = response.json()
        for slot in data:
            start = datetime.fromisoformat(slot["startTime"].replace('Z', '+00:00'))
>           assert start.date() >= datetime.fromisoformat(from_date).date()
E           AssertionError: assert datetime.date(2026, 7, 5) >= datetime.date(2026, 7, 6)
E            +  where datetime.date(2026, 7, 5) = <built-in method date of datetime.datetime object at 0x000002347FAD94D0>()
E            +    where <built-in method date of datetime.datetime object at 0x000002347FAD94D0> = datetime.datetime(2026, 7, 5, 14, 0).date
E            +  and   datetime.date(2026, 7, 6) = <built-in method date of datetime.datetime object at 0x000002347FAD9560>()
E            +    where <built-in method date of datetime.datetime object at 0x000002347FAD9560> = datetime.datetime(2026, 7, 6, 0, 0).date
E            +      where datetime.datetime(2026, 7, 6, 0, 0) = <built-in method fromisoformat of type object at 0x00007FFD240A5270>('2026-07-06')
E            +        where <built-in method fromisoformat of type object at 0x00007FFD240A5270> = datetime.fromisoformat

test_api.py:83: AssertionError
_____________________________________________ test_create_booking_duplicate ______________________________________________

test_slot = '5ff5461a-bcb8-48b9-b90d-8c7a6463369b'

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
>       assert response2.status_code == 409  # или 400, ожидаем ошибку
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       assert 200 == 409
E        +  where 200 = <Response [200 OK]>.status_code

test_api.py:160: AssertionError
____________________________________________ test_cancel_booking_after_start _____________________________________________

test_slot = 'b32aefce-4dc7-477f-b046-f728f0fe7154'

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
>       assert "Cannot cancel after start" in response.text
E       assert 'Cannot cancel after start' in '{"detail":"Cannot cancel less than 10 minutes before start"}'
E        +  where '{"detail":"Cannot cancel less than 10 minutes before start"}' = <Response [400 Bad Request]>.text

test_api.py:239: AssertionError
================================================ short test summary info =================================================
FAILED test_api.py::test_get_slots_filter - AssertionError: assert datetime.date(2026, 7, 5) >= datetime.date(2026, 7, 6)
FAILED test_api.py::test_create_booking_duplicate - assert 200 == 409
FAILED test_api.py::test_cancel_booking_after_start - assert 'Cannot cancel after start' in '{"detail":"Cannot cancel less than 10 minutes before start"}'
============================================== 3 failed, 11 passed in 0.48s ==============================================
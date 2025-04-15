import json
from datetime import datetime, timedelta
import pandas as pd

class Client:
    def __init__(self, id, location, needs, schedule, funding, availability, accept_new_employee,
                 service_type, prefer_known_employee, affinity):
        self.id = id
        self.location = location
        self.needs = needs
        self.schedule = schedule
        self.funding = funding
        self.availability = availability
        self.accept_new_employee = accept_new_employee
        self.service_type = service_type
        self.prefer_known_employee = prefer_known_employee
        self.affinity = affinity

class Employee:
    def __init__(self, id, location, weekly_hours, qualifications, availability, clients_assigned,
                 transport, work_schedule, vacations, leaves, trainings, rqth, key_time, known_clients,
                 affinity, max_days_per_week):
        self.id = id
        self.location = location
        self.weekly_hours = weekly_hours
        self.qualifications = qualifications
        self.availability = availability
        self.clients_assigned = clients_assigned
        self.transport = transport
        self.work_schedule = work_schedule
        self.vacations = vacations
        self.leaves = leaves
        self.trainings = trainings
        self.rqth = rqth
        self.key_time = key_time
        self.known_clients = known_clients
        self.affinity = affinity
        self.max_days_per_week = max_days_per_week

class Planning:
    def __init__(self):
        self.assignments = []

    def add_assignment(self, client_id, employee_id, datetime, task, duration):
        self.assignments.append({
            "client_id": client_id,
            "employee_id": employee_id,
            "datetime": datetime,
            "task": task,
            "duration": duration
        })

    def calculate_employee_hours(self, all_employee_ids):
        hours = {str(emp_id): 0 for emp_id in all_employee_ids}
        for assignment in self.assignments:
            employee_id = str(assignment["employee_id"])
            hours[employee_id] += assignment["duration"]
        return hours

    def export_to_file(self, filename="planning.json", all_employee_ids=None):
        if all_employee_ids is None:
            all_employee_ids = []
        output = {
            "assignments": self.assignments,
            "employee_hours": self.calculate_employee_hours(all_employee_ids)
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4, default=str)
        print(f"Planning exporté vers {filename}")

COMPATIBLE_QUALIFICATIONS = {
    "meal_preparation": ["cooking", "caregiver"],
    "cleaning": ["housekeeping"],
    "personal_care": ["caregiver"],
    "groceries": ["caregiver"],
    "appointment_transport": ["caregiver"]
}

def calculate_distance(loc1, loc2):
    return abs(hash(str(loc1)) - hash(str(loc2))) % 100

def get_slot_duration(time_slot):
    try:
        start_str, end_str = time_slot.split("-")
        start_time = datetime.strptime(start_str, "%H:%M")
        end_time = datetime.strptime(end_str, "%H:%M")
        duration = (end_time - start_time).total_seconds() / 3600
        return duration
    except Exception as e:
        print(f"Erreur calcul durée créneau {time_slot}: {e}")
        return 1

def is_employee_available(employee, assignment_date, time_slot):
    try:
        start_time = datetime.strptime(time_slot.split("-")[0], "%H:%M")
        end_time = datetime.strptime(time_slot.split("-")[1], "%H:%M")
        assignment_date = assignment_date.date()

        for vacation in employee.vacations:
            start = datetime.strptime(vacation["start"], "%Y-%m-%d").date()
            end = datetime.strptime(vacation["end"], "%Y-%m-%d").date()
            if start <= assignment_date <= end:
                print(f"Salarié {employee.id} indisponible: en vacances du {start} au {end}")
                return False

        for leave in employee.leaves:
            start = datetime.strptime(leave["start"], "%Y-%m-%d").date()
            end = datetime.strptime(leave["end"], "%Y-%m-%d").date()
            if start <= assignment_date <= end:
                print(f"Salarié {employee.id} indisponible: en congé/arrêt du {start} au {end}")
                return False

        for training in employee.trainings:
            training_date = datetime.strptime(training["date"], "%Y-%m-%d").date()
            if training_date != assignment_date:
                continue
            training_start = datetime.strptime(training["start_time"], "%H:%M")
            training_end = datetime.strptime(training["end_time"], "%H:%M")
            if not (end_time.time() <= training_start.time() or start_time.time() >= training_end.time()):
                print(f"Salarié {employee.id} indisponible: en formation le {training_date} de {training_start} à {training_end}")
                return False

        return True
    except Exception as e:
        print(f"Erreur vérification disponibilité salarié {employee.id}: {e}")
        return False

def is_time_compatible(client_schedule, employee_availability, task, other_interventions, assigned_times, employee):
    print(f"Vérification compatibilité pour tâche: {task}")
    for day, times in client_schedule.items():
        if day not in employee_availability:
            print(f"Jour {day} non disponible pour le salarié")
            continue
        for time_slot in times:
            try:
                start_time = datetime.strptime(time_slot.split("-")[0], "%H:%M")
                print(f"Analyse créneau: {time_slot}, heure début: {start_time}")
                if task == "meal_preparation" and start_time.hour < 10:
                    print(f"Rejet: repas trop tôt à {start_time.hour}h")
                    continue
                conflict = False
                for intervention in other_interventions:
                    intervention_time = datetime.strptime(intervention["time"], "%H:%M")
                    time_diff = abs((start_time - intervention_time).total_seconds()) / 60
                    if time_diff < 60:
                        print(f"Conflit avec intervention à {intervention['time']}")
                        conflict = True
                        break
                if conflict:
                    continue
                for assignment in assigned_times:
                    if assignment["day"] != day:
                        continue
                    assignment_time = datetime.strptime(assignment["time"].split("-")[0], "%H:%M")
                    time_diff = abs((start_time - assignment_time).total_seconds()) / 60
                    if time_diff < 60 + employee.key_time:
                        print(f"Conflit avec autre affectation à {assignment['time']} (incl. key_time)")
                        conflict = True
                        break
                if conflict:
                    continue
                print(f"Créneau compatible trouvé: {day}, {time_slot}")
                return day, time_slot
            except Exception as e:
                print(f"Erreur dans l'analyse du créneau {time_slot}: {e}")
    print("Aucun créneau compatible")
    return None, None

def generate_planning(clients, employees, other_interventions):
    planning = Planning()
    print("Début génération planning")
    employee_assigned_times = {emp.id: [] for emp in employees}
    unassigned_clients = []

    for client in clients:
        print(f"Traitement client {client.id}")
        best_employee = None
        min_score = float('inf')
        best_time = None
        best_day = None
        best_duration = None

        for employee in employees:
            print(f"Vérification salarié {employee.id}")
            if client.id not in employee.known_clients and not client.accept_new_employee:
                print(f"Salarié {employee.id} rejeté: client n'accepte pas nouveaux employés")
                continue
            compatible = True
            requires_car = "groceries" in client.needs or "appointment_transport" in client.needs
            if requires_car and employee.transport != "car":
                print(f"Salarié {employee.id} rejeté: voiture requise pour {client.needs}")
                compatible = Fal"se
                continue
            for need in client.needs:
                required_quals = COMPATIBLE_QUALIFICATIONS.get(need, [need])
                if not any(qual in employee.qualifications for qual in required_quals):
                    print(f"Salarié {employee.id} rejeté: manque qualification pour {need}")
                    compatible = False
                    break
            if not compatible:
                continue
            affinity_score = 0
            if employee.id in client.affinity.get("preferred_employee_ids", []) or \
               client.id in employee.affinity.get("preferred_client_ids", []):
                affinity_score = 1
                print(f"Salarié {employee.id} prioritaire (affinité)")
            day, compatible_time = is_time_compatible(client.schedule, employee.availability,
                                                    client.service_type, other_interventions,
                                                    employee_assigned_times[employee.id], employee)
            if compatible_time:
                base_date = datetime(2025, 4, 14) if day == "Monday" else datetime(2025, 4, 15)
                if not is_employee_available(employee, base_date, compatible_time):
                    print(f"Salarié {employee.id} rejeté: indisponible à cette date")
                    continue
                distance = calculate_distance(client.location, employee.location)
                qualif_bonus = 0.25 if "cooking" in employee.qualifications and client.service_type == "meal_preparation" else 1
                workload_penalty = 1 + 0.1 * len(employee_assigned_times[employee.id])
                score = (distance / 10 if affinity_score == 1 else distance * 2) * qualif_bonus * workload_penalty
                print(f"Score calculé: {score} (distance: {distance}, affinité: {affinity_score}, qualif_bonus: {qualif_bonus}, workload: {workload_penalty})")
                if score < min_score:
                    min_score = score
                    best_employee = employee
                    best_time = compatible_time
                    best_day = day
                    best_duration = get_slot_duration(compatible_time)
                    print(f"Nouveau meilleur salarié: {employee.id} (score: {score}, duration: {best_duration})")

        if best_employee and best_time and best_day:
            base_date = datetime(2025, 4, 14) if best_day == "Monday" else datetime(2025, 4, 15)
            assignment_time = datetime.strptime(f"{base_date.strftime('%Y-%m-%d')} {best_time.split('-')[0]}", "%Y-%m-%d %H:%M")
            planning.add_assignment(client.id, best_employee.id, assignment_time, client.service_type, best_duration)
            employee_assigned_times[best_employee.id].append({"time": best_time, "day": best_day})
            print(f"Affectation ajoutée: Client {client.id}, Salarié {best_employee.id}, {assignment_time}, durée: {best_duration}h")
        else:
            unassigned_clients.append(client.id)
            print(f"Échec affectation pour client {client.id}")

    if unassigned_clients:
        print(f"AVERTISSEMENT : Clients sans prestation : {unassigned_clients}")

    return planning

if __name__ == "__main__":
    clients = [
        Client(
            id=1,
            location={"city": "Paris", "zip": "75001"},
            needs=["meal_preparation"],
            schedule={"Monday": ["12:00-13:00"], "Tuesday": ["12:00-13:00"]},
            funding="APA",
            availability={"Monday": ["08:00-20:00"], "Tuesday": ["08:00-20:00"]},
            accept_new_employee=True,
            service_type="meal_preparation",
            prefer_known_employee=False,
            affinity={"preferred_employee_ids": [1]}
        ),
        Client(
            id=2,
            location={"city": "Paris", "zip": "75003"},
            needs=["cleaning"],
            schedule={"Monday": ["14:00-15:00"]},
            funding="CARSAT",
            availability={"Monday": ["08:00-20:00"]},
            accept_new_employee=False,
            service_type="cleaning",
            prefer_known_employee=True,
            affinity={"preferred_employee_ids": [2]}
        ),
        Client(
            id=3,
            location={"city": "Paris", "zip": "75005"},
            needs=["personal_care", "groceries"],
            schedule={"Tuesday": ["10:00-12:00"]},
            funding="MDPH",
            availability={"Tuesday": ["08:00-20:00"]},
            accept_new_employee=True,
            service_type="personal_care",
            prefer_known_employee=False,
            affinity={"preferred_employee_ids": []}
        ),
        Client(
            id=4,
            location={"city": "Paris", "zip": "75001"},
            needs=["meal_preparation"],
            schedule={"Monday": ["12:00-13:00"], "Tuesday": ["12:00-13:00"]},
            funding="APA",
            availability={"Monday": ["08:00-20:00"], "Tuesday": ["08:00-20:00"]},
            accept_new_employee=True,
            service_type="meal_preparation",
            prefer_known_employee=False,
            affinity={"preferred_employee_ids": []}
        )
    ]

    employees = [
        Employee(
            id=1,
            location={"city": "Paris", "zip": "75002"},
            weekly_hours=35,
            qualifications=["caregiver", "cooking"],
            availability={"Monday": ["08:00-17:00"], "Tuesday": ["08:00-17:00"]},
            clients_assigned=[1, 3],
            transport="car",
            work_schedule={},
            vacations=[],
            leaves=[],
            trainings=[],
            rqth=False,
            key_time=15,
            known_clients=[1, 3],
            affinity={"preferred_client_ids": [1]},
            max_days_per_week=5
        ),
        Employee(
            id=2,
            location={"city": "Paris", "zip": "75004"},
            weekly_hours=20,
            qualifications=["housekeeping", "caregiver"],
            availability={"Monday": ["10:00-18:00"], "Tuesday": ["10:00-18:00"]},
            clients_assigned=[2],
            transport="public",
            work_schedule={},
            vacations=[],
            leaves=[],
            trainings=[],
            rqth=True,
            key_time=10,
            known_clients=[2],
            affinity={"preferred_client_ids": [2]},
            max_days_per_week=4
        ),
        Employee(
            id=3,
            location={"city": "Paris", "zip": "75006"},
            weekly_hours=30,
            qualifications=["caregiver"],
            availability={"Monday": ["08:00-19:00"], "Tuesday": ["08:00-19:00"]},
            clients_assigned=[],
            transport="car",
            work_schedule={},
            vacations=[{"start": "2025-04-14", "end": "2025-04-15"}],  #Changer au 2025-04-24 pour montrer que ça fonctionne
            leaves=[],
            trainings=[],
            rqth=False,
            key_time=20,
            known_clients=[],
            affinity={"preferred_client_ids": []},
            max_days_per_week=5
        )
    ]

    other_interventions = [
        {"time": "08:00", "type": "nurse"},
        {"time": "09:00", "type": "doctor"}
    ]

    planning = generate_planning(clients, employees, other_interventions)
    planning.export_to_file("planning_result.json", all_employee_ids=[emp.id for emp in employees])
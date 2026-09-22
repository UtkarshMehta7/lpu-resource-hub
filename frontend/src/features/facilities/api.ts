import type { Page } from "@/features/directory/api";
import { apiClient } from "@/lib/api/client";

export type MaintenanceStatus = "available" | "maintenance" | "retired";
export type BookingStatus = "pending" | "approved" | "rejected" | "cancelled" | "completed";

export const MAINTENANCE_LABEL: Record<MaintenanceStatus, string> = {
  available: "Available",
  maintenance: "Under maintenance",
  retired: "Retired",
};

export const BOOKING_STATUS_LABEL: Record<BookingStatus, string> = {
  pending: "Awaiting approval",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Cancelled",
  completed: "Completed",
};

export interface Facility {
  id: string;
  name: string;
  description: string | null;
  department_id: string | null;
  location: string | null;
  contact: string | null;
  equipment_count: number;
  created_at: string;
}

export interface Equipment {
  id: string;
  facility_id: string;
  facility_name: string;
  department_id: string | null;
  name: string;
  description: string | null;
  category: string | null;
  maintenance_status: MaintenanceStatus;
  students_allowed: boolean;
  requires_approval: boolean;
  max_hours: number;
  min_lead_hours: number;
  created_at: string;
}

export interface BusySlot {
  starts_at: string;
  ends_at: string;
  is_mine: boolean;
}

export interface Availability {
  equipment_id: string;
  maintenance_status: MaintenanceStatus;
  students_allowed: boolean;
  requires_approval: boolean;
  max_hours: number;
  min_lead_hours: number;
  busy: BusySlot[];
}

export interface Booking {
  id: string;
  equipment_id: string;
  equipment_name: string;
  facility_name: string;
  user_id: string;
  user_name: string;
  starts_at: string;
  ends_at: string;
  purpose: string;
  status: BookingStatus;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string;
}

function clean(params: object): Record<string, unknown> {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== ""));
}

export async function fetchFacilities(filters: {
  q?: string;
  department_id?: string;
  page?: number;
}): Promise<Page<Facility>> {
  const response = await apiClient.get<Page<Facility>>("/api/v1/facilities", {
    params: clean(filters),
  });
  return response.data;
}

export async function fetchFacility(id: string): Promise<Facility> {
  const response = await apiClient.get<Facility>(`/api/v1/facilities/${id}`);
  return response.data;
}

export async function fetchEquipmentList(filters: {
  facility_id?: string;
  category?: string;
  q?: string;
  page?: number;
}): Promise<Page<Equipment>> {
  const response = await apiClient.get<Page<Equipment>>("/api/v1/equipment", {
    params: clean(filters),
  });
  return response.data;
}

export async function fetchEquipment(id: string): Promise<Equipment> {
  const response = await apiClient.get<Equipment>(`/api/v1/equipment/${id}`);
  return response.data;
}

export async function createEquipment(input: {
  facility_id: string;
  name: string;
  category?: string | null;
  description?: string | null;
  students_allowed: boolean;
  requires_approval: boolean;
  max_hours: number;
  min_lead_hours: number;
}): Promise<Equipment> {
  const response = await apiClient.post<Equipment>("/api/v1/equipment", input);
  return response.data;
}

export async function fetchAvailability(
  equipmentId: string,
  from: string,
  to: string,
): Promise<Availability> {
  const response = await apiClient.get<Availability>(
    `/api/v1/equipment/${equipmentId}/availability`,
    { params: { from, to } },
  );
  return response.data;
}

export async function createBooking(input: {
  equipment_id: string;
  starts_at: string;
  ends_at: string;
  purpose: string;
}): Promise<Booking> {
  const response = await apiClient.post<Booking>("/api/v1/bookings", input);
  return response.data;
}

export async function fetchMyBookings(status?: BookingStatus): Promise<Booking[]> {
  const response = await apiClient.get<Booking[]>("/api/v1/me/bookings", {
    params: status ? { status } : undefined,
  });
  return response.data;
}

export async function fetchBookingQueue(): Promise<Booking[]> {
  const response = await apiClient.get<Booking[]>("/api/v1/coordinator/booking-queue");
  return response.data;
}

export async function decideBooking(
  id: string,
  action: "approve" | "reject",
  note: string | null,
): Promise<Booking> {
  const response = await apiClient.post<Booking>(`/api/v1/bookings/${id}/${action}`, { note });
  return response.data;
}

export async function cancelBooking(id: string): Promise<Booking> {
  const response = await apiClient.post<Booking>(`/api/v1/bookings/${id}/cancel`);
  return response.data;
}

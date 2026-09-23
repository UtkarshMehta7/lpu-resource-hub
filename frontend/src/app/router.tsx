import { createBrowserRouter } from "react-router-dom";

import { AdminCreateAccountPage } from "@/features/admin/AdminCreateAccountPage";
import { AdminHandoverPage } from "@/features/admin/AdminHandoverPage";
import { AdministrationPage } from "@/features/admin/AdministrationPage";
import { AdminUsersPage } from "@/features/admin/AdminUsersPage";
import { CoordinatorsPage } from "@/features/admin/CoordinatorsPage";
import { OrganisationPage } from "@/features/admin/OrganisationPage";
import { DirectoryPage } from "@/features/directory/DirectoryPage";
import { ResearcherDetailPage } from "@/features/directory/ResearcherDetailPage";
import { StudentsPage } from "@/features/directory/StudentsPage";
import { AccountPage } from "@/features/auth/AccountPage";
import { AdminLoginPage } from "@/features/auth/AdminLoginPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import { RoleRoute } from "@/features/auth/RoleRoute";
import { HomePage } from "@/features/home/HomePage";
import { NotFoundPage } from "@/features/home/NotFoundPage";
import { OnboardingPage } from "@/features/onboarding/OnboardingPage";
import { ProjectDetailPage } from "@/features/projects/ProjectDetailPage";
import { ProjectFormPage } from "@/features/projects/ProjectFormPage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { ReviewQueuePage } from "@/features/projects/ReviewQueuePage";
import { FundingDetailPage } from "@/features/funding/FundingDetailPage";
import { FundingFormPage } from "@/features/funding/FundingFormPage";
import { FundingPage } from "@/features/funding/FundingPage";
import { NotificationsPage } from "@/features/notifications/NotificationsPage";
import { BookingQueuePage } from "@/features/facilities/BookingQueuePage";
import { EquipmentDetailPage } from "@/features/facilities/EquipmentDetailPage";
import { EquipmentFormPage } from "@/features/facilities/EquipmentFormPage";
import { FacilityFormPage } from "@/features/facilities/FacilityFormPage";
import { FacilitiesPage } from "@/features/facilities/FacilitiesPage";
import { FacilityDetailPage } from "@/features/facilities/FacilityDetailPage";
import { MyBookingsPage } from "@/features/facilities/MyBookingsPage";
import { ChangePasswordRequiredPage } from "@/features/auth/ChangePasswordRequiredPage";
import { AnalyticsPage } from "@/features/analytics/AnalyticsPage";
import { AuditLogPage } from "@/features/admin/AuditLogPage";
import { PlatformSettingsPage } from "@/features/admin/PlatformSettingsPage";
import { CreateAccountPage } from "@/features/admin/CreateAccountPage";
import { PeoplePage } from "@/features/admin/PeoplePage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { ModerationQueuePage } from "@/features/reports/ModerationQueuePage";
import { SavedPage } from "@/features/saved/SavedPage";
import { SearchPage } from "@/features/search/SearchPage";
import { RecommendationsPage } from "@/features/recommendations/RecommendationsPage";
import { CollaborationsPage } from "@/features/collaborations/CollaborationsPage";
import { ApplicantsPage } from "@/features/opportunities/ApplicantsPage";
import { MyApplicationsPage } from "@/features/opportunities/MyApplicationsPage";
import { OpportunitiesPage } from "@/features/opportunities/OpportunitiesPage";
import { OpportunityDetailPage } from "@/features/opportunities/OpportunityDetailPage";
import { OpportunityFormPage } from "@/features/opportunities/OpportunityFormPage";
import { PublicationDetailPage } from "@/features/publications/PublicationDetailPage";
import { PublicationFormPage } from "@/features/publications/PublicationFormPage";
import { PublicationsPage } from "@/features/publications/PublicationsPage";
import { ProfilePage } from "@/features/profiles/ProfilePage";
import { VerificationQueuePage } from "@/features/researchers/VerificationQueuePage";

import { AppLayout } from "./layouts/AppLayout";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "login", element: <LoginPage /> },
      // A separate entrance for administrators. Not a separate set of
      // permissions: the role on the account is still what decides.
      { path: "admin/login", element: <AdminLoginPage /> },
      {
        element: <ProtectedRoute />,
        children: [
          { path: "account", element: <AccountPage /> },
          { path: "set-password", element: <ChangePasswordRequiredPage /> },
          { path: "researchers", element: <DirectoryPage /> },
          { path: "researchers/:userId", element: <ResearcherDetailPage /> },
          { path: "onboarding", element: <OnboardingPage /> },
          { path: "projects", element: <ProjectsPage /> },
          { path: "projects/mine", element: <ProjectsPage mine /> },
          { path: "projects/:projectId", element: <ProjectDetailPage /> },
          { path: "projects/:projectId/edit", element: <ProjectFormPage /> },
          { path: "publications", element: <PublicationsPage /> },
          { path: "opportunities", element: <OpportunitiesPage /> },
          { path: "opportunities/mine", element: <OpportunitiesPage mine /> },
          { path: "opportunities/:opportunityId", element: <OpportunityDetailPage /> },
          { path: "opportunities/:opportunityId/edit", element: <OpportunityFormPage /> },
          { path: "opportunities/:opportunityId/applicants", element: <ApplicantsPage /> },
          { path: "me/applications", element: <MyApplicationsPage /> },
          { path: "collaborations", element: <CollaborationsPage /> },
          { path: "search", element: <SearchPage /> },
          { path: "recommendations", element: <RecommendationsPage /> },
          { path: "dashboard", element: <DashboardPage /> },
          { path: "me/saved", element: <SavedPage /> },
          { path: "facilities", element: <FacilitiesPage /> },
          { path: "facilities/:facilityId", element: <FacilityDetailPage /> },
          { path: "equipment/:equipmentId", element: <EquipmentDetailPage /> },
          { path: "me/bookings", element: <MyBookingsPage /> },
          { path: "funding", element: <FundingPage /> },
          { path: "funding/:fundingId", element: <FundingDetailPage /> },
          { path: "me/notifications", element: <NotificationsPage /> },
          { path: "publications/mine", element: <PublicationsPage mine /> },
          { path: "publications/:publicationId", element: <PublicationDetailPage /> },
          { path: "publications/:publicationId/edit", element: <PublicationFormPage /> },
          { path: "profile", element: <ProfilePage /> },
          {
            element: <RoleRoute allow={["research_coordinator", "admin"]} />,
            children: [
              { path: "coordinator/verification-queue", element: <VerificationQueuePage /> },
              { path: "coordinator/review-queue", element: <ReviewQueuePage /> },
              { path: "admin/reports", element: <ModerationQueuePage /> },
              { path: "analytics", element: <AnalyticsPage /> },
              { path: "coordinator/booking-queue", element: <BookingQueuePage /> },
              { path: "facilities/new", element: <FacilityFormPage /> },
              { path: "funding/new", element: <FundingFormPage /> },
              {
                path: "facilities/:facilityId/equipment/new",
                element: <EquipmentFormPage />,
              },
            ],
          },
          {
            element: <RoleRoute allow={["faculty", "research_coordinator", "admin"]} />,
            children: [
              { path: "students", element: <StudentsPage /> },
              { path: "people", element: <PeoplePage /> },
              { path: "people/new", element: <CreateAccountPage /> },
            ],
          },
          {
            element: <RoleRoute allow={["faculty", "research_coordinator"]} />,
            children: [
              { path: "projects/new", element: <ProjectFormPage /> },
              { path: "publications/new", element: <PublicationFormPage /> },
              { path: "opportunities/new", element: <OpportunityFormPage /> },
            ],
          },
          {
            element: <RoleRoute allow={["admin"]} />,
            children: [
              { path: "admin", element: <AdministrationPage /> },
              { path: "admin/coordinators", element: <CoordinatorsPage /> },
              { path: "admin/administrators", element: <AdminHandoverPage /> },
              { path: "admin/accounts/new", element: <AdminCreateAccountPage /> },
              { path: "admin/organisation", element: <OrganisationPage /> },
              { path: "admin/users", element: <AdminUsersPage /> },
              { path: "admin/audit-logs", element: <AuditLogPage /> },
              { path: "admin/settings", element: <PlatformSettingsPage /> },
            ],
          },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

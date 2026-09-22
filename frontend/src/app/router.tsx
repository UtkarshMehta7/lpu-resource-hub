import { createBrowserRouter } from "react-router-dom";

import { AdminUsersPage } from "@/features/admin/AdminUsersPage";
import { DirectoryPage } from "@/features/directory/DirectoryPage";
import { ResearcherDetailPage } from "@/features/directory/ResearcherDetailPage";
import { StudentsPage } from "@/features/directory/StudentsPage";
import { AccountPage } from "@/features/auth/AccountPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { RoleRoute } from "@/features/auth/RoleRoute";
import { HomePage } from "@/features/home/HomePage";
import { NotFoundPage } from "@/features/home/NotFoundPage";
import { OnboardingPage } from "@/features/onboarding/OnboardingPage";
import { ProjectDetailPage } from "@/features/projects/ProjectDetailPage";
import { ProjectFormPage } from "@/features/projects/ProjectFormPage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { ReviewQueuePage } from "@/features/projects/ReviewQueuePage";
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
      { path: "register", element: <RegisterPage /> },
      {
        element: <ProtectedRoute />,
        children: [
          { path: "account", element: <AccountPage /> },
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
          { path: "publications/mine", element: <PublicationsPage mine /> },
          { path: "publications/:publicationId", element: <PublicationDetailPage /> },
          { path: "publications/:publicationId/edit", element: <PublicationFormPage /> },
          { path: "profile", element: <ProfilePage /> },
          {
            element: <RoleRoute allow={["research_coordinator", "admin"]} />,
            children: [
              { path: "coordinator/verification-queue", element: <VerificationQueuePage /> },
              { path: "coordinator/review-queue", element: <ReviewQueuePage /> },
            ],
          },
          {
            element: <RoleRoute allow={["faculty", "research_coordinator", "admin"]} />,
            children: [{ path: "students", element: <StudentsPage /> }],
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
            children: [{ path: "admin/users", element: <AdminUsersPage /> }],
          },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

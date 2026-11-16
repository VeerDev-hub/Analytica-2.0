import { Navigate, createBrowserRouter, RouterProvider } from 'react-router-dom';
import { AppShell } from './AppShell.jsx';
import { AuthGate } from './AuthGate.jsx';
import { HomePage } from '../features/home/HomePage.jsx';
import { AuthPage, OAuthCallback } from '../features/auth/AuthPage.jsx';
import { ProjectsPage } from '../features/projects/ProjectsPage.jsx';
import { ProjectIndex, ProjectLayout } from '../features/project/ProjectLayout.jsx';
import { DataPage } from '../features/project/DataPage.jsx';
import { ExplorePage } from '../features/project/ExplorePage.jsx';
import { StepsPage } from '../features/project/StepsPage.jsx';
import { AssistantPage, ExportPage, ValidatePage } from '../features/project/OtherPages.jsx';
import { RecipesPage } from '../features/recipes/RecipesPage.jsx';
import { AdminPage } from '../features/admin/AdminPage.jsx';
import { AccountPage } from '../features/account/AccountPage.jsx';

const router = createBrowserRouter([
  // Public pages
  { path: '/', element: <HomePage /> },
  { path: '/login', element: <AuthPage mode="login" /> },
  { path: '/register', element: <AuthPage mode="register" /> },
  { path: '/auth/callback', element: <OAuthCallback /> },
  // Signed-in app
  {
    element: <AuthGate />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: 'projects', element: <ProjectsPage /> },
          {
            path: 'projects/:projectId',
            element: <ProjectLayout />,
            children: [
              { index: true, element: <ProjectIndex /> },
              { path: 'data', element: <DataPage /> },
              { path: 'explore', element: <ExplorePage /> },
              { path: 'clean', element: <StepsPage key="clean" kind="clean" /> },
              { path: 'features', element: <StepsPage key="features" kind="features" /> },
              { path: 'validate', element: <ValidatePage /> },
              { path: 'export', element: <ExportPage /> },
              { path: 'assistant', element: <AssistantPage /> },
            ],
          },
          { path: 'recipes', element: <RecipesPage /> },
          { path: 'admin', element: <AdminPage /> },
          { path: 'account', element: <AccountPage /> },
          { path: '*', element: <Navigate to="/projects" replace /> },
        ],
      },
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}

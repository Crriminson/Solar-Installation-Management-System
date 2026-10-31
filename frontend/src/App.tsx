/*
  Routes.

  One place listing every screen in the app and the URL it lives at.
  Add a route here when you add a page.
*/

import { Routes, Route } from "react-router-dom";

import { EmptyMessage } from "./components/StateMessage";
import LoginPage from "./features/auth/LoginPage";
import RequireStaff from "./features/auth/RequireStaff";
import EnquiryForm from "./features/enquiries/EnquiryForm";
import SalesQueue from "./features/enquiries/SalesQueue";
import SurveyList from "./features/surveys/SurveyList";
import SurveyRecord from "./features/surveys/SurveyRecord";
import SurveyStepForm from "./features/surveys/SurveyStepForm";
import MyWorkPage from "./features/work/MyWorkPage";

export default function App() {
  return (
    <Routes>
      {/* Public: the enquiry form anyone can reach. */}
      <Route path="/" element={<EnquiryForm />} />
      <Route path="/login" element={<LoginPage />} />

      {/* Staff: inside the app frame, after signing in. */}
      <Route element={<RequireStaff />}>
        <Route path="/work" element={<MyWorkPage />} />
        <Route path="/enquiries" element={<SalesQueue />} />
        <Route path="/enquiries/new" element={<EnquiryForm staff />} />
        <Route path="/surveys" element={<SurveyList />} />
        <Route path="/surveys/:surveyId" element={<SurveyRecord />} />
        <Route path="/surveys/:surveyId/new" element={<SurveyStepForm />} />
      </Route>

      <Route path="*" element={<EmptyMessage>This page does not exist.</EmptyMessage>} />
    </Routes>
  );
}

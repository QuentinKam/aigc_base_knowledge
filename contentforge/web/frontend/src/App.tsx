import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import HomePage from "./pages/HomePage";
import Demo1SingleTopic from "./pages/Demo1SingleTopic";
import Demo2CustomQuestion from "./pages/Demo2CustomQuestion";
import Demo3Batch from "./pages/Demo3Batch";
import Demo4Inject from "./pages/Demo4Inject";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/demo1" element={<Demo1SingleTopic />} />
        <Route path="/demo2" element={<Demo2CustomQuestion />} />
        <Route path="/demo3" element={<Demo3Batch />} />
        <Route path="/demo4" element={<Demo4Inject />} />
      </Routes>
    </Layout>
  );
}

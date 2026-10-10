const tasks = [
  {
    id: 1,
    title: "create Homepage wirefame",
    description: "designing the wireframe",
    label: "Design",
    status: "todo",
    dueDate: "12-10-2026",
  },
  {
    id: 2,
    title: "market research for Yarnanimal.in",
    description: "market research for Yarnanimal.in",
    label: "Market Research",
    status: "todo",
    dueDate: "13-10-2026",
  },
  {
    id: 3,
    title: "Talk to yarn animals developer",
    description: "Talk to yarn animals developer",
    label: "Communication",
    status: "todo",
    dueDate: "11-10-2026",
  },
  {
    id: 4,
    title: "Raise complaint with AWS",
    description: "Raise complaint with AWS",
    label: "Tools",
    status: "done",
    dueDate: "09-10-2026",
  },
  {
    id: 5,
    title: "Ask for social media credentials and create strategy",
    description: "Ask for social media credentials and create strategy",
    label: "Strategy",
    status: "in-progress",
    dueDate: "15-10-2026",
  },
];

function render() {
  const listToDo = document.getElementById("list-todo");
  const listProgress = document.getElementById("list-progress");
  const listDone = document.getElementById("list-done");

  listDone = "";
  listProgress = "";
  listToDo = "";

  tasks.forEach(function (task) {
    const card = `
  <article class="task-card">
    <div class="task-top">
      <span class="task-label ${task.color}">${task.label}</span>
      <button type="button">•••</button>
    </div>
    <h3>${task.title}</h3>
    <p>${task.description}</p>
    <div class="task-footer">
      <span class="due-date">◷ ${task.dueDate}</span>
    </div>
  </article>
`;

    console.log(card);
  });
}

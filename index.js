const tasks = [
  {
    id: 1,
    title: "create Homepage wirefame",
    description: "designing the wireframe",
    label: "Design",
    status: "todo",
    color: "purple",
    dueDate: "2026-10-12",
  },
  {
    id: 2,
    title: "market research for Yarnanimal.in",
    description: "market research for Yarnanimal.in",
    label: "Market Research",
    status: "todo",
    color: "purple",
    dueDate: "2026-10-13",
  },
  {
    id: 3,
    title: "Talk to yarn animals developer",
    description: "Talk to yarn animals developer",
    label: "Communication",
    status: "todo",
    color: "purple",
    dueDate: "2026-10-11",
  },
  {
    id: 4,
    title: "Raise complaint with AWS",
    description: "Raise complaint with AWS",
    label: "Tools",
    status: "done",
    color: "green",
    dueDate: "2026-10-09",
  },
  {
    id: 5,
    title: "Ask for social media credentials and create strategy",
    description: "Ask for social media credentials and create strategy",
    label: "Strategy",
    status: "progress",
    color: "orange",
    dueDate: "2026-10-15",
  },
];

const dialog = document.getElementById("task-dialog");
const form = document.getElementById("task-form");

function render() {
  let listToDo = document.getElementById("list-todo");
  let listProgress = document.getElementById("list-progress");
  let listDone = document.getElementById("list-done");

  listDone.innerHTML = "";
  listProgress.innerHTML = "";
  listToDo.innerHTML = "";

  tasks.forEach(function (task) {
    let card = `
  <article class="task-card" data-id="${task.id}" >
    <div class="task-top">
      <span class="task-label ${task.color}">${task.label}</span>
      <button type="button" class="menu-btn">•••</button>
    </div>
    <h3>${task.title}</h3>
    <p>${task.description}</p>
    <div class="task-footer">
      <span class="due-date">◷ ${task.dueDate}</span>
    </div>
    <div class="card-actions">${getActionButtons(task)}</div>
  </article>
`;

    if (task.status === "done") {
      card = `
  <article class="task-card completed-card" data-id="${task.id}">
    <div class="task-top">
      <span class="task-label green-label">${task.label}</span>
      <button type="button" class="menu-btn">•••</button>
    </div>
    <h3>${task.title}</h3>
    <p>${task.description}</p>
    <div class="task-footer">
      <span class="done-date">✓ Completed</span>
    </div>
    <div class="card-actions">${getActionButtons(task)}</div>
  </article>
`;
    } else {
      card = `
  <article class="task-card">
    <div class="task-top">
      <span class="task-label ${task.color}">${task.label}</span>
      <button type="button" class="menu-btn">•••</button>
    </div>
    <h3>${task.title}</h3>
    <p>${task.description}</p>
    <div class="task-footer">
      <span class="due-date">◷ ${task.dueDate}</span>
    </div>
    <div class="card-actions">${getActionButtons(task)}</div>
  </article>
`;
    }

    if (task.status === "todo") {
      listToDo.innerHTML += card;
    } else if (task.status === "progress") {
      listProgress.innerHTML += card;
    } else if (task.status === "done") {
      listDone.innerHTML += card;
    }
  });
}

document.getElementById("add-task-btn").addEventListener("click", function () {
  document.getElementById("task-status").value = "todo";
  dialog.showModal();
});

document.querySelectorAll(".column-add").forEach(function (btn) {
  btn.addEventListener("click", function () {
    document.getElementById("task-status").value = btn.dataset.status;
    dialog.showModal();
  });
});

document.getElementById("cancel-btn").addEventListener("click", function () {
  dialog.close();
});

form.addEventListener("submit", function (event) {
  event.preventDefault();

  const newTask = {
    id: Date.now(),
    title: document.getElementById("task-title").value,
    description: document.getElementById("task-desc").value,
    label: document.getElementById("task-label").value,
    color: document.getElementById("task-color").value,
    status: document.getElementById("task-status").value,
    dueDate: document.getElementById("task-date").value,
  };

  tasks.push(newTask);
  render();
  form.reset();
  dialog.close();
});

function getActionButtons(task) {
  if (task.status === "todo") {
    return `<button type="button" class="action-btn" data-action="start">▶ Start</button>`;
  } else if (task.status === "progress") {
    return `
      <button type="button" class="action-btn" data-action="complete">✓ Done</button>
      <button type="button" class="action-btn secondary" data-action="back">↩ Back</button>`;
  } else {
    return `<button type="button" class="action-btn secondary" data-action="reopen">↩ Reopen</button>`;
  }
}

document
  .querySelector(".kanban-columns")
  .addEventListener("click", function (event) {
    const button = event.target.closest(".action-btn");
    if (!button) return;

    const card = button.closest(".task-card");
    const id = Number(card.dataset.id);
    const task = tasks.find(function (t) {
      return t.id === id;
    });
    const action = button.dataset.action;

    if (action === "start") {
      task.status = "progress";
      task.startedAt = Date.now();
    } else if (action === "complete") {
      task.status = "done";
      task.completedAt = Date.now();
    } else if (action === "back") {
      task.status = "todo";
      task.startedAt = null;
    } else if (action === "reopen") {
      task.status = "progress";
      task.startedAt = Date.now();
      task.completedAt = null;
    }
  });

render();

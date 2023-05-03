import {
    html,
    render,
    useState,
    useCallback,
    useEffect,
} from "./preact_htm.js";


/* A simple counter. */
function useCounter(initialValue=0) {
  const [count, setCount] = useState(initialValue);
  const increment = useCallback(() => setCount(count => count + 1), []);
  return [count, increment];
}


/* A list of names known to the API (or null) */
function useNames() {
  const [names, setNames] = useState(null);
  useEffect(async () => {
    setNames(await (await fetch("../api/names")).json())
  }, []);
  return names;
}

/* A list of memories for a given name. Set forceReload to different values to
 * force a reload of the memories.
 */
function useMemories(name, forceReload) {
  const [memories, setMemories] = useState(null);
  useEffect(async () => {
    setMemories(await (await fetch(`../api/memories/${name}`)).json())
    return () => setMemories(null);
  }, [name, forceReload]);
  return memories;
}

/* A form for entering new memories. */
function NewMemory({name, onNewMemory}) {
  const todayIsoDate = new Date().toISOString().substring(0, 10);
  
  const onSubmit = useCallback((evt) => {
    evt.preventDefault();
    
    (async () => {
      const res = await fetch(
        `../api/memories/${name}`,
        {
          method: "POST",
          body: new FormData(evt.target),
        }
      );
      if (res.ok) {
        const id = await res.json();
        window.location.hash = `#${name}/${id}`;
        evt.target.reset();
        if (onNewMemory) {
          onNewMemory(id);
        }
      } else {
        alert("Something went wrong saving the memory... Try again later.");
        console.error(await res.text());
      }
    })();
  }, [name]);
  
  
  return html`
    <form onSubmit=${onSubmit} class="NewMemory">
      <input type="date" name="date" value=${todayIsoDate} required></input>
      <input type="text" name="note" placeholder="What did ${name} do?"></textarea>
      <input type="submit" value="Add"></input>
    </form>
  `;
}

function MemoryItem({name, date, note, years, months, days}) {
  return html`${note}`
}

/* A list of memories. */
function MemoryList({name="", forceReload=null}) {
  const memories = useMemories(name, forceReload);
  if (memories === null) {
    return "Loading memories...";
  }
  
  const memoriesByAge = [];
  for (const memory of memories) {
    let currentAge = memoriesByAge[memoriesByAge.length - 1] || [];
    const currentExample = currentAge[0] || {};
    if (memory.years !== currentExample.years || memory.months !== currentExample.months) {
      currentAge = [];
      memoriesByAge.push(currentAge);
    }
    currentAge.push(memory);
  }
  
  return html`
    <div class="MemoryList">
      ${memoriesByAge.map(memories => {
        let age;
        if (memories[0].years === 0 && memories[0].months === 0) {
          age = "newborn";
        } else if (memories[0].years === 0) {
          age = `${memories[0].months} month${memories[0].months !== 1 ? 's' : ''}`;
        } else if (memories[0].months === 0) {
          age = `${memories[0].years} year${memories[0].years !== 1 ? 's' : ''}`;
        } else {
          age = `${memories[0].years} year${memories[0].years !== 1 ? 's' : ''}, `;
          age += `${memories[0].months} month${memories[0].months !== 1 ? 's' : ''}`;
        }
        
        return html`
          <div key="${memories[0].years}-${memories[0].months}">
            <h2>${age}</h2>
            <ul>
              ${memories.map(memory => html`
                <li><${MemoryItem} key=${memory.id} ...${memory}/></li>
              `)}
            </ul>
          </div>
        `;
      })}
    </div>
  `;
}


/* Hook returning window.location.hash. */
function useHash() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const cb = () => setHash(window.location.hash);
    addEventListener("hashchange", cb);
    return () => removeEventListener("hashchange", cb);
  }, [])
  
  return hash;
}

/* List of names to pick from. */
function NameList() {
  const names = useNames();
  if (names === null) {
    return html`Loading...`;
  }
  
  const onAddNew = useCallback(evt => {
    const name = prompt("Enter new name:")
    if (name) {
      window.location.hash = `#${name}/`;
    }
    evt.preventDefault();
  }, []);
  
  return html`
    <ul class="NameList">
      ${names.map(name => html`
        <li><a href="#${name}">${name}</a></li>
      `)}
      <li class="new"><a href="#" onClick=${onAddNew}>Add new person</a></li>
    </ul>
  `;
}

function Main() {
  const hash = useHash();
  const [forceReload, setForceReload] = useCounter();
  
  let title, body;
  
  const match = hash.match(/^#([^/]+)(\/.*)?$/);
  if (match) {
    const name = match[1];
    title = `Memories of ${name}`;
    body = html`
      <${MemoryList} name=${name} forceReload=${forceReload} />
      <${NewMemory} name=${name} onNewMemory=${setForceReload}/>
    `;
  } else {
    title = `Memories of...`;
    body = html`
      <${NameList} />
    `;
  }
  
  return html`
    <header>
      <h1>${title}</h1>
    </header>
    ${body}
  `;
}


render(html`<${Main} />`, document.body);

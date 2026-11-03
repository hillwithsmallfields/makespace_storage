<script>
function select_version(container_id, choice) {
    var container = document.getElementById(container_id);
    var choices = container.getElementsByClassName('choice');
    for (let i=0; i<choices.length; i++) {
        if (choices[i].getAttribute('name') === choice) {
            choices[i].style.display = 'block';
        } else {
            choices[i].style.display = 'none';
        }
    }
    buttons = container.getElementsByTagName('button');
    for (let i=0; i<buttons.length; i++) {
        if (buttons[i].getAttribute('name') === choice) {
            buttons[i].className = 'active';
        } else {
            buttons[i].className = 'inactive';
        }
    }
}

function find_item() {
    item_name = document.getElementById('item').value;
    fetch(`http://127.0.0.1:8000/where/${item_name}`).then((response) => {
        return response.json();
    }).then((json) => {
        console.log(json.location);
        document.getElementById('location').innerHTML = json.location;
    }).catch((err) => console.error('Fetch problem: ${err.message}'))
}

function inspect_item() {
    item_name = document.getElementById('item').value;
    fetch(`http://127.0.0.1:8000/details/${item_name}`).then((response) => {
        return response.json();
    }).then((json) => {
        // this will be more subtle, as there will be assorted keys
        console.log(json.location);
        document.getElementById('location').innerHTML = json.location;
    }).catch((err) => console.error('Fetch problem: ${err.message}'))
}

function place_item() {
    item_name = document.getElementById('item').value;
    place_name = document.getElementById('place').value;
    fetch(`http://127.0.0.1:8000/store/${item_name}/${place_name}`).then((response) => {
        return response.json();
    }).then((json) => {
        console.log(json.location);
        document.getElementById('location').innerHTML = json.location;
    }).catch((err) => console.error('Fetch problem: ${err.message}'))
}

function startup() {
    select_version('one_page_app_switcher', 'Find');
}
</script>
